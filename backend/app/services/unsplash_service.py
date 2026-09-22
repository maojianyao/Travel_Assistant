#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : unsplash_service.py
@Time    : 2026/9/18 15:05
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
import logging

import requests

from backend.app.config import get_settings
from typing import List, Optional


class UnsplashService:
    """Unsplash图片服务类"""

    def __init__(self):
        """初始化服务"""
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        self.base_url = "https://api.unsplash.com"

    def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        """
        搜索图片
        :param query: 搜索关键词
        :param per_page: 每页图片数量
        :return: 图片列表
        """
        try:
            url = f"{self.base_url}/search/photos"
            params = {
                "query": query,
                "per_page": per_page,
                "client_id": self.access_key,
                "orientation": "landscape",
                "content_filter": "high",     # 过滤低质量/不适宜内容
                "order_by": "relevant",       # 按相关性排序（默认）
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            # 提取照片
            photos = []
            for photo in results:
                photo_data = {
                    "id": photo.get("id"),
                    "url": photo.get("urls", {}).get("regular"),
                    "thumb": photo.get("urls", {}).get("thumb"),
                    "description": photo.get("description", {}) or photo.get("alt_description"),
                    "photographer": photo.get("user", {}).get("name")
                }
                photos.append(photo_data)
            return photos
        except Exception as e:
            logging.info(f"Unsplash 搜索失败：{str(e)}")
            return []

    def get_photo_url(self, query: str) -> Optional[str]:
        """
        获取单张图片URL
        :param query: 搜索关键词
        :return: 图片URL
        """
        photos = self.search_photos(query, 1)
        return photos[0].get("url", {}) if photos else None


_unsplash_service = None

def get_unsplash_service() -> UnsplashService:
    global _unsplash_service
    if _unsplash_service is None:
        _unsplash_service = UnsplashService()
    return _unsplash_service



if __name__ == '__main__':
    # service = get_unsplash_service()
    # print(service.search_photos("sunset", 3))

    unsplash_service = get_unsplash_service()
    name = ["芙蓉广场"]
    for n in name:
        # 搜索景点图片
        photo_url = unsplash_service.get_photo_url(query=f"{n} China landmark")
        if not photo_url:
            # 如果没有找到，尝试只用景点名称搜索
            photo_url = unsplash_service.get_photo_url(query=n)
        print(photo_url)







