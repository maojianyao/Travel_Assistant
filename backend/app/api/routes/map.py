#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : map.py
@Time    : 2026/9/18 12:32
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
from fastapi.params import Query

from backend.app.models.schemas import POISearchResponse, WeatherResponse, RouteResponse, RouteRequest
from fastapi import APIRouter, HTTPException
from backend.app.services.amap_service import get_amap_service

router = APIRouter(prefix='/map', tags=['地图服务'])

@router.get(
    '/poi',
    response_model=POISearchResponse,
    summary='POI搜索',
    description="根据关键词搜索POI（兴趣点）"
)
async def search_poi(keywords: str = Query(..., description="搜索关键词"),
                     city: str = Query(..., description="城市名称"),
                     citylimit: bool = Query(True, description="是否限制在城市范围内")):
    """根据关键词搜索POI（兴趣点）"""
    try:
        amap_service = get_amap_service()
        pois = amap_service.search_poi(keywords, city, citylimit)
        return POISearchResponse(success=True, message="POI搜索成功", data=pois)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"POI搜索失败: {str(e)}")


@router.get('/weather',
            response_model=WeatherResponse,
            summary="查询天气",
            description="查询指定城市的天气信息")
async def get_weather(city: str = Query(..., description='城市名称', examples=["北京"])):
    """
    查询天气
    :param city: 城市名称
    :return: 天气信息，包括温度、天气情况、风向风力等
    """
    try:
        amap_service = get_amap_service()

        weather_info = amap_service.get_weather(city)
        return WeatherResponse(success=True, message="天气查询成功", data=weather_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"天气查询失败：{str(e)}")


@router.post('/route',
             response_model=RouteResponse,
             summary="规划路线",
             description="规划两点之间的路线")
async def plan_route(request: RouteRequest):
    """
    规划路线
    :param request: 路线规划请求参数
    :return: 路线信息，包括路线坐标、距离、时间等
    """
    try:
        amap_service = get_amap_service()
        route_info = amap_service.plan_route(**request.model_dump())
        return RouteResponse(success=True, message="路线规划成功", data=route_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"路线规划失败：{str(e)}")


@router.get("/health",
            summary="健康检查",
            description="检查地图服务是否正常")
async def health_check():
    """健康检查"""
    try:
        amap_service = get_amap_service()
        result = amap_service.check_health()
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用：{str(e)}")