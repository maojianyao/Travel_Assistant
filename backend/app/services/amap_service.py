#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : amap_service.py
@Time    : 2026/9/18 12:34
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
import threading
import time
from typing import List, Optional, Dict, Any

import httpx
from loguru import logger

from backend.app.config import get_settings
from backend.app.models.schemas import POIInfo, WeatherInfo, Location, RouteInfo


class AmapServiceError(Exception):
    """高德地图服务调用异常"""


class QpsLimiter:
    """线程安全的全局QPS限流器(按最小请求间隔串行放行, 并发调用自动排队)"""

    def __init__(self, qps: float):
        self._min_interval = 1.0 / max(float(qps), 0.1)
        self._lock = threading.Lock()
        self._next_allowed_time = 0.0

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            wait_seconds = self._next_allowed_time - now
            self._next_allowed_time = max(now, self._next_allowed_time) + self._min_interval
        if wait_seconds > 0:
            time.sleep(wait_seconds)


class AmapService:
    """高德地图服务封装类"""

    BASE_URL = "https://restapi.amap.com"

    # 常见错误码补充说明
    INFO_CODE_HINTS = {
        "10001": "Key不存在或已过期，请检查AMAP_API_KEY配置",
        "10003": "当日调用量已超限",
        "10009": "Key类型与所调服务不匹配，需申请Web服务类型的Key",
        "10044": "账号当日调用量已超限",
        "10021": "并发量超限(触发QPS限流)，服务会自动重试",
        "20803": "起终点距离超出该路线类型的规划范围上限（步行最大100公里），请检查起终点地址是否正确或更换路线类型",
    }

    # 触发QPS限流时可重试的错误码
    QPS_LIMIT_INFO_CODES = {"10019", "10020", "10021", "10022"}
    # QPS超限后的最大尝试次数
    MAX_RETRIES = 3

    def __init__(self):
        self._settings = get_settings()
        self._client = httpx.Client(timeout=10)
        self._qps_limiter = QpsLimiter(qps=self._settings.qps_limit)

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        调用高德Web服务API并返回JSON结果
        :param path: 接口路径，如 /v3/place/text
        :param params: 请求参数
        :return: 响应JSON数据
        """
        if not self._settings.amap_api_key:
            raise AmapServiceError("AMAP_API_KEY未配置")

        request_params = dict(params or {})
        request_params["key"] = self._settings.amap_api_key
        url = f"{self.BASE_URL}{path}"

        last_error_message = ""
        for attempt in range(self.MAX_RETRIES):
            # 请求前排队限流: 并发工具调用在此按最小间隔串行放行, 避免瞬时并发超过QPS
            self._qps_limiter.acquire()
            try:
                response = self._client.get(url, params=request_params)
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.error(f"高德API请求失败: {url}, error: {e}")
                raise AmapServiceError(f"高德API请求失败: {e}") from e

            if "errcode" in data and "status" not in data:
                # v4系列接口（如骑行路径规划）使用errcode表示状态，0代表成功
                if data.get("errcode") != 0:
                    errmsg = data.get("errmsg") or data.get("errdetail") or "UNKNOWN_ERROR"
                    logger.error(f"高德API返回错误: {url}, {errmsg}")
                    raise AmapServiceError(f"高德API返回错误: {errmsg}")
                return data

            if str(data.get("status")) != "1":
                info = data.get("info") or "UNKNOWN_ERROR"
                infocode = str(data.get("infocode")) or ""
                hint = self.INFO_CODE_HINTS.get(infocode, "")
                message = f"高德API返回错误: {info}({infocode})"
                if hint:
                    message = f"{message}，{hint}"
                last_error_message = message
                # QPS超限: 指数退避后重试
                if infocode in self.QPS_LIMIT_INFO_CODES and attempt < self.MAX_RETRIES - 1:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(f"触发QPS限流, {backoff}秒后重试(第{attempt + 2}/{self.MAX_RETRIES}次): {url}")
                    time.sleep(backoff)
                    continue

                logger.error(f"{message} {url}")
                raise AmapServiceError(message)
            return data
        raise AmapServiceError(f"重试{self.MAX_RETRIES}次后仍失败, {last_error_message} {url}")

    @staticmethod
    def _clean_field(value: Any) -> str:
        """
        将高德API返回的字段统一转换为字符串，空值或空列表返回空字符串
        :param value: 原始字段值
        :return: 字符串
        """
        if isinstance(value, list):
            return ",".join(str(item) for item in value if item)
        return str(value) if value is not None else ""

    @staticmethod
    def _parse_location(location: str) -> Optional[Location]:
        """
        解析"经度,纬度"格式的字符串为Location对象
        :param location: 经纬度字符串，如 "116.39747,39.90923"
        :return: Location对象，解析失败返回None
        """
        location = AmapService._clean_field(location)
        if "," not in location:
            return None
        try:
            longitude, latitude = location.split(",", 1)
            return Location(longitude=float(longitude), latitude=float(latitude))
        except ValueError:
            return None

    @classmethod
    def _extract_route_path(cls, value: Any) -> List[Location]:
        """从高德路线结果中的 polyline 字段提取、去重坐标。"""
        polylines: List[str] = []

        def collect(item: Any) -> None:
            if isinstance(item, dict):
                polyline = item.get("polyline")
                if isinstance(polyline, str):
                    polylines.append(polyline)
                for child in item.values():
                    collect(child)
            elif isinstance(item, list):
                for child in item:
                    collect(child)

        collect(value)
        path: List[Location] = []
        for polyline in polylines:
            for point in polyline.split(";"):
                location = cls._parse_location(point)
                if location and (not path or path[-1] != location):
                    path.append(location)
        return path

    def _geocode_raw(self, address: str, city: Optional[str] = None) -> Dict[str, Any]:
        """
        调用地理编码接口并返回第一条编码结果
        :param address: 地址
        :param city: 城市
        :return: 地理编码结果，无结果时返回空字典
        """
        params = {"address": address}
        if city:
            params["city"] = city
        data = self._request("/v3/geocode/geo", params)
        geocodes = data.get("geocodes") or []
        return geocodes[0] if geocodes else {}

    def _get_adcode(self, city: str) -> str:
        """
        获取城市的adcode（区域编码），天气查询接口必须传入adcode
        :param city: 城市名称或adcode
        :return: adcode
        """
        city = str(city).strip()
        if city.isdigit() and len(city) == 6:
            return city
        adcode = self._geocode_raw(city).get("adcode") or ""
        if not adcode:
            raise AmapServiceError(f"无法获取城市的adcode: {city}")
        return adcode

    def search_poi(self, keywords: str, city: str, citylimit: bool=True) -> List[POIInfo]:
        """
        根据关键词和城市搜索POI信息
        :param keywords: 搜索关键词
        :param city: 城市
        :param citylimit: 是否限制在城市范围内
        :return: POI信息列表
        """
        params = {
            "keywords": keywords,
            "city": city,
            "citylimit": str(citylimit).lower(),
            "offset": 20,
            "page": 1,
            "extensions": "base",
        }
        data = self._request("/v3/place/text", params)
        results: List[POIInfo] = []
        for poi in data.get("pois") or []:
            location = self._parse_location(poi.get("location", ""))
            if location is None:
                continue
            tel = self._clean_field(poi.get("tel"))
            results.append(
                POIInfo(
                    id=self._clean_field(poi.get("id")),
                    name=self._clean_field(poi.get("name")),
                    type=self._clean_field(poi.get("type")),
                    address=self._clean_field(poi.get("address")),
                    location=location,
                    tel=tel or None,
                )
            )
        return results

    def get_weather(self, city: str) -> List[WeatherInfo]:
        """
        查询天气信息
        :param city: 城市
        :return: 天气信息列表
        """
        adcode = self._get_adcode(city)
        data = self._request("/v3/weather/weatherInfo", {"city": adcode, "extensions": "all"})
        forecasts = data.get("forecasts") or []
        if not forecasts:
            return []
        weather_list: List[WeatherInfo] = []
        for cast in forecasts[0].get("casts") or []:
            weather_list.append(
                WeatherInfo(
                    date=self._clean_field(cast.get("date")),
                    day_weather=self._clean_field(cast.get("dayweather")),
                    night_weather=self._clean_field(cast.get("nightweather")),
                    day_temp=self._clean_field(cast.get("daytemp")) or 0,
                    night_temp=self._clean_field(cast.get("nighttemp")) or 0,
                    wind_direction=self._clean_field(cast.get("daywind")),
                    wind_power=self._clean_field(cast.get("daypower")),
                )
            )
        return weather_list


    def plan_route(self,
                   origin_address: str,
                   destination_address: str,
                   origin_city: Optional[str] = None,
                   destination_city: Optional[str] = None,
                   route_type: str = 'walking') -> RouteInfo:
        """
        规划路线
        :param origin_address: 起点地址
        :param destination_address: 终点地址
        :param origin_city: 起点城市
        :param destination_city: 终点城市
        :param route_type: 路线类型（'walking'、'driving'、'transit'）
        :return: 路线信息
        """
        origin_geo = self._geocode_raw(origin_address, origin_city)
        origin_location = self._parse_location(origin_geo.get("location", ""))
        if origin_location is None:
            raise AmapServiceError(f"无法解析起点地址: {origin_address}")
        destination_geo = self._geocode_raw(destination_address, destination_city or origin_city)
        destination_location = self._parse_location(destination_geo.get("location", ""))
        if destination_location is None:
            raise AmapServiceError(f"无法解析终点地址: {destination_address}")

        origin = f"{origin_location.longitude},{origin_location.latitude}"
        destination = f"{destination_location.longitude},{destination_location.latitude}"
        route_type = (route_type or "walking").lower()

        if route_type == "walking":
            data = self._request("/v3/direction/walking", {"origin": origin, "destination": destination})
            paths = (data.get("route") or {}).get("paths") or []
            if not paths:
                raise AmapServiceError("未找到可行的步行路线")
            distance = float(paths[0].get("distance") or 0)
            duration = int(float(paths[0].get("duration") or 0))
            description = (f"从{origin_address}步行至{destination_address}，"
                           f"全程约{distance / 1000:.1f}公里，预计耗时{duration // 60}分钟")
            path = self._extract_route_path(paths[0])
        elif route_type == "driving":
            data = self._request("/v3/direction/driving",
                                 {"origin": origin, "destination": destination, "extensions": "base"})
            paths = (data.get("route") or {}).get("paths") or []
            if not paths:
                raise AmapServiceError("未找到可行的驾车路线")
            distance = float(paths[0].get("distance") or 0)
            duration = int(float(paths[0].get("duration") or 0))
            description = (f"从{origin_address}驾车至{destination_address}，"
                           f"全程约{distance / 1000:.1f}公里，预计耗时{duration // 60}分钟")
            path = self._extract_route_path(paths[0])
        elif route_type == "transit":
            start_city = origin_city or self._clean_field(origin_geo.get("city"))
            if not start_city:
                raise AmapServiceError("公交路线规划需要指定起点城市")
            params = {"origin": origin, "destination": destination, "city": start_city, "extensions": "base"}
            destination_adcode = destination_city or self._clean_field(destination_geo.get("city"))
            if destination_adcode and destination_adcode != start_city:
                params["cityd"] = destination_adcode
            data = self._request("/v3/direction/transit/integrated", params)
            route_data = data.get("route") or {}
            transits = route_data.get("transits") or []
            if not transits:
                raise AmapServiceError("未找到可行的公交路线")
            transit = transits[0]
            distance = float(route_data.get("distance") or 0)
            duration = int(float(transit.get("duration") or 0))
            walking_distance = float(transit.get("walking_distance") or 0)
            description = (f"从{origin_address}乘坐公共交通至{destination_address}，"
                           f"预计耗时{duration // 60}分钟，步行约{walking_distance:.0f}米")
            path = self._extract_route_path(transit)
        elif route_type == "bicycling":
            data = self._request("/v4/direction/bicycling", {"origin": origin, "destination": destination})
            paths = (data.get("data") or {}).get("paths") or []
            if not paths:
                raise AmapServiceError("未找到可行的骑行路线")
            distance = float(paths[0].get("distance") or 0)
            duration = int(float(paths[0].get("duration") or 0))
            description = (f"从{origin_address}骑行至{destination_address}，"
                           f"全程约{distance / 1000:.1f}公里，预计耗时{duration // 60}分钟")
            path = self._extract_route_path(paths[0])
        else:
            raise AmapServiceError(f"不支持的路线类型: {route_type}")

        return RouteInfo(
            distance=distance,
            duration=duration,
            route_type=route_type,
            description=description,
            path=path,
        )

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """
        地理编码
        :param address: 地址
        :param city: 城市
        :return: 经纬度坐标
        """
        return self._parse_location(self._geocode_raw(address, city).get("location", ""))


    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
       """
       根据POI ID获取POI详情
       :param poi_id: POI ID
       :return: POI详情
       """

       data = self._request("/v3/place/detail", {"id": poi_id})
       pois = data.get("pois") or []
       if not pois:
           raise AmapServiceError(f"未找到POI详情: {poi_id}")
       return pois[0]

    def check_health(self) -> Dict[str, Any]:
        """
        检查高德地图服务是否可用（校验Key配置、网络连通性与Key有效性）
        :return: {"available": 是否可用, "message": 说明信息}
        """
        if not self._settings.amap_api_key:
            logger.warning("健康检查失败: AMAP_API_KEY未配置")
            return {"available": False, "message": "AMAP_API_KEY未配置，请在.env中配置后重试"}

        try:
            # 使用地理编码接口探测：请求轻量，且是本服务的核心依赖接口
            data = self._request("/v3/geocode/geo", {"address": "北京市"})
        except AmapServiceError as e:
            return {"available": False, "message": f"高德地图服务不可用: {str(e)}"}

        if not (data.get("geocodes") or []):
            return {"available": False, "message": "高德地图服务响应异常: 地理编码无结果"}

        logger.info("高德地图服务健康检查通过")
        return {"available": True, "message": "高德地图服务可用"}

_amap_service =None

def get_amap_service() -> AmapService:
    """
    获取高德地图服务实例（单例模式）
    :return:
    """
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()

    return _amap_service


if __name__ == '__main__':
    amap_service = get_amap_service()
    # weather = amap_service.get_weather("长沙望城区")
    # print(weather)
    # plan_route = amap_service.plan_route("长沙市望城区澳海澜庭",'4号线湘江新城地铁口', "长沙")
    # print(plan_route)

    poi = amap_service.search_poi('历史文化 图书馆', '长沙' )
    print(poi)
    # poi_detail = amap_service.get_poi_detail("B02DB02GD3")
    # print(poi_detail)
    #
    # print(amap_service.check_health())