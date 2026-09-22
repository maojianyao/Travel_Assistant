#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : schemas.py
@Time    : 2026/9/18 08:59
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
from typing import Optional, Union, List

from pydantic import BaseModel, Field, field_validator, model_validator


###======请求类型======###
class TripRequest(BaseModel):
    """旅行规划请求"""
    city: str = Field(..., description="目的地城市", examples=['北京'])
    start_date: str = Field(..., description="开始日期", examples=["2025-06-01"])
    end_date: str = Field(..., description="结束日期", examples=["2025-06-03"])
    travel_days: int = Field(..., description="旅程天数", ge=1, le=30, examples=[3])
    transportation: str = Field(..., description="交通方式", examples=["公共交通"])
    accommodation: str = Field(..., description="住宿偏好", examples=["经济型酒店"])
    preferences: list[str] = Field(default=[], description="旅行偏好标签", examples=["历史文化", "美食"])
    free_text_input: Optional[str] = Field(default="", description="额外要求", examples=["希望多安排一些博物馆"])

    class Config:
        json_schema_extra = {
            "example": {
                "city": "北京",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "travel_days": 3,
                "transportation": "公共交通",
                "accommodation": "经济型酒店",
                "preferences": ["历史文化", "美食"],
                "free_text_input": "希望多安排一些博物馆"
            }
        }


class POISearchRequest(BaseModel):
    """POI搜索请求"""
    keywords: str = Field(..., description="搜索关键词", examples=["博物馆"])
    city: str = Field(..., description="目的地城市", examples=["北京"])
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class RouteRequest(BaseModel):
    """路线规划请求"""
    origin_address: str = Field(..., description="起点地址", examples=["北京市朝阳区阜通东大街6号"])
    destination_address: str = Field(..., description="终点地址", examples=["北京市海淀区上地十街10号"])
    origin_city: Optional[str] = Field(default=None, description="起点城市")
    destination_city: Optional[str] = Field(default=None, description="终点城市")
    route_type: str = Field(default="walking", description="路线类型", examples=["driving", "walking", "transit", "bicycling"])


###======响应类型类型======###

class Location(BaseModel):
    """地理位置"""
    latitude: float = Field(..., description="纬度", examples=[39.90923])
    longitude: float = Field(..., description="经度", examples=[116.39747])


class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(..., description="景点名称", examples=["故宫"])
    address: str = Field(..., description="景点地址", examples=["北京市朝阳区"])
    location: Location = Field(..., description="景点位置的经纬度")
    visit_duration: int = Field(..., description="建议游览时长（分钟）", examples=[60])
    description: Optional[str] = Field(default=None, description="景点描述", examples=["世界上最大的宫殿"])
    category: Optional[str] = Field(default="景点", description="景点类别", examples=["博物馆"])
    rating: Optional[float] = Field(default=None, description="景点评分", examples=[4.5])
    photos: Optional[list[str]] = Field(default_factory=list, description="景点照片的URL列表")
    # review_count: Optional[int] = Field(default=None, description="评价数量", examples=[1234])
    poi_id: Optional[str] = Field(default=None, description="POI ID")
    image_url: Optional[str] = Field(default=None, description="景点图片的URL")
    ticket_price: int = Field(default=0, description="门票价格（元）")


class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(..., description="餐饮类型", examples=["breakfast", "lunch", "dinner", "snack"])
    name: str = Field(..., description="餐饮名称", examples=["海底捞"])
    address: Optional[str] = Field(default=None, description="餐饮地址")
    location: Optional[Location] = Field(default=None, description="餐饮位置的经纬度")
    description: Optional[str] = Field(default=None, description="餐饮描述", examples=[" delicious food"])
    # rating: Optional[float] = Field(default=None, description="餐饮评分", examples=[4.5])
    estimated_cost: int = Field(default=0, description="预计消费（元）")


class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(..., description="酒店名称", examples=["如家酒店"])
    address: str = Field(default="", description="酒店地址")
    location: Optional[Location] = Field(default=None, description="酒店位置的经纬度")
    price_range: str = Field(default="", description="价格范围")
    rating: str = Field(default="", description="酒店评分")
    distance: str = Field(default="", description="距离景点距离")
    type: str = Field(default="", description="酒店类型")
    # photos: Optional[list[str]] = Field(default_factory=list, description="酒店照片的URL列表")
    estimated_cost: int = Field(default=0, description="预计消费（元/晚）")


class DayPlan(BaseModel):
    """每日行程计划"""
    date: str = Field(..., description="日期 yyyy-mm-dd")
    day_index: int = Field(..., description="第几天(从0开始)")
    description: str = Field(..., description="当日行程描述")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿方式")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: list[Attraction] = Field(default=[], description="景点列表")
    meals: list[Meal] = Field(default=[], description="餐饮列表")

    @model_validator(mode="before")
    @classmethod
    def normalize_hotel_key(cls, data):
        """兼容LLM输出hotels键名, 统一映射为hotel"""
        if isinstance(data, dict) and "hotel" not in data and "hotels" in data:
            data["hotel"] = data.pop("hotels")
        return data


class WeatherInfo(BaseModel):
    """天气信息"""
    date: str = Field(..., description="日期 yyyy-mm-dd")
    day_weather: str = Field(..., description="白天天气情况")
    night_weather: str = Field(..., description="夜晚天气情况")
    day_temp: Union[str, int] = Field(default=0, description="白天温度")
    night_temp: Union[str, int] = Field(default=0, description="夜晚温度")
    wind_direction: str = Field(default="", description="风向", examples=["东北风"])
    wind_power: str = Field(default="", description="风力", examples=["3级"])

    @field_validator("day_temp", "night_temp", mode="before")
    @classmethod
    def parse_temperature(cls, value):
        """解析温度，移除等°C单位"""
        if isinstance(value, str):
            # 移除°C, ℃等单位符号，只保留数字
            value = value.replace("℃", "").replace("°C", "").replace("°", "")
            try:
                return int(value)
            except ValueError:
                return 0
        return value


class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class TripPlan(BaseModel):
    """旅行计划"""
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期 yyyy-mm-dd")
    end_date: str = Field(..., description="结束日期 yyyy-mm-dd")
    days: List[DayPlan] = Field(..., description="每日行程")
    weather_info: List[WeatherInfo] = Field(default=[], description="天气信息")
    overall_suggestions: str = Field(..., description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")
    is_fallback: bool = Field(default=False, description="是否为兜底示例行程(AI生成失败时)")


class TripPlanResponse(BaseModel):
    """旅游计划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")
    trip_id: Optional[str] = Field(default=None, description="行程ID, 用于再次查看与分享")


class TripListItem(BaseModel):
    """行程历史列表项"""
    trip_id: str = Field(..., description="行程ID")
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    travel_days: int = Field(..., description="旅行天数")
    is_fallback: bool = Field(default=False, description="是否为示例行程")
    created_at: str = Field(..., description="创建时间")


class TripListResponse(BaseModel):
    """行程历史列表响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[TripListItem] = Field(default=[], description="行程列表")


class TripDetailResponse(BaseModel):
    """行程详情响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    trip_id: Optional[str] = Field(default=None, description="行程ID")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")


class POIInfo(BaseModel):
    """POI信息"""
    id: str = Field(..., description="POI ID")
    name: str = Field(..., description="名称")
    type: str = Field(..., description="类型")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="位置的经纬度")
    tel: Optional[str] = Field(default=None, description="POI电话")


class POISearchResponse(BaseModel):
    """POI搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[List[POIInfo]] = Field(default=None, description="POI信息列表")


class RouteInfo(BaseModel):
    """路线信息"""
    distance: float = Field(..., description="距离（米）")
    duration: int = Field(..., description="路线耗时（秒）")
    route_type: str = Field(..., description="路线类型")
    description: str = Field(..., description="路线描述")
    path: List[Location] = Field(
        default_factory=list,
        description="用于地图绘制的路线坐标，按行进顺序排列",
    )


class RouteResponse(BaseModel):
    """路线规划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[RouteInfo] = Field(default=None, description="路线信息")


class WeatherResponse(BaseModel):
    """天气响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[List[WeatherInfo]] = Field(default=None, description="天气信息")


###======= 错误响应 ==========###

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(default=False, description="是否成功")
    message: str = Field(..., description="错误消息")
    error_code: Optional[str] = Field(default=None, description="错误码")
