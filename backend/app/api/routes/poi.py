#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : poi.py
@Time    : 2026/9/18 12:32
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.amap_service import get_amap_service
from backend.app.services.unsplash_service import get_unsplash_service

router = APIRouter(prefix='/poi', tags=["POI"])

class POIDetailResponse(BaseModel):
    """POI详情响应"""
    success: bool
    message: str
    data: Optional[dict] = None


@router.get(
    "/detail/{poi_id}",
    response_model=POIDetailResponse,
    summary="获取POI详情",
    description="根据POI ID获取详细信息，包括图片"
)
async def get_poi_detail(poi_id: str) -> POIDetailResponse:
    """
    获取POI详情
    :param poi_id: POI ID
    :return: POI详情
    """
    try:
        amap_service = get_amap_service()
        poi_detail = amap_service.get_poi_detail(poi_id)
        return POIDetailResponse(success=True, message="POI详情获取成功", data=poi_detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"POI详情获取失败: {str(e)}")


@router.get(
    "/search",
    summary="搜索POI",
    description="根据关键词搜索POI"
)
async def search_poi(keywords:str, city:str) -> dict:
    """搜索POI
    :param keywords: 关键词
    :param city: 城市
    :return: POI搜索结果
    """
    try:
        amap_service = get_amap_service()
        poi_search_result = amap_service.search_poi(keywords, city)
        return {"success": True, "message": "POI搜索成功", "data": poi_search_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"POI搜索失败: {str(e)}")

# 景点图片缓存: 同名景点复用首次查询结果(无图结果也缓存, 避免反复搜索)
_photo_cache: dict = {}


@router.get(
    "/photo",
    summary="获取景点图片",
    description="根据景点名称从Unsplash获取图片"
)
async def get_attraction_photo(name: str):
    """
    获取景点图片
    :param name: 景点名称
    :return: 景点图片url
    """
    try:
        if name in _photo_cache:
            return {"success": True, "message": "景点图片获取成功", "data": {"name": name, "photo_url": _photo_cache[name]}}

        unsplash_service = get_unsplash_service()
        # 搜索景点图片
        photo_url = unsplash_service.get_photo_url(query=f"{name} China landmark")
        if not photo_url:
            # 如果没有找到，尝试只用景点名称搜索
            photo_url = unsplash_service.get_photo_url(query=name)
        _photo_cache[name] = photo_url
        return {"success": True, "message": "景点图片获取成功", "data": {"name": name, "photo_url": photo_url}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"景点图片获取失败: {str(e)}")




