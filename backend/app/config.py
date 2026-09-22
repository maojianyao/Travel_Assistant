#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : config.py
@Time    : 2026/9/17 20:37
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 尝试加载.env
load_dotenv()


class Settings(BaseSettings):
    """应用配置"""

    # 针对高德API的QPS限制
    qps_limit: int = 3
    # 应用基本配置
    app_name: str = "智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = False

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # 数据存储配置(SQLite)
    database_path: str = "data/trips.db"

    # CORS配置 - 使用字符串，在代码中分割
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # 高德地图API配置
    amap_api_key: str =""

    # Unsplash API配置
    unsplash_access_key: str = ""
    unsplash_secret_key: str = ""

    # LLM配置（从环境变量中读取）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-5.6"

    # 日志配置
    log_level:str = "INFO"

    class Config:
        env_file = '.env'
        case_sensitive = False
        extra = "ignore"  # 忽略额外的环境变量

    def get_cors_origins_list(self):
        """获取CORS origins列表"""
        return [origin.strip() for origin in self.cors_origins.split(',')]


settings = Settings()

def get_settings() -> Settings:
    """获取配置实例"""
    return settings


def validate_config():
    """ 验证配置是否完整"""
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY未配置")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        warnings.append("LLM_API_KEY或OPENAI_API_KEY未配置,LLM功能可能无法使用")

    if errors:
        error_msg = "配置错误:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    if warnings:
        print("\n⚠️  配置警告:")
        for w in warnings:
            print(f"  - {w}")

    return True


def print_config():
    """打印配置信息"""
    print(f"应用名称: {settings.app_name}")
    print(f"版本: {settings.app_version}")
    print(f"服务器: {settings.host}:{settings.port}")
    print(f"CORS Origins: {settings.cors_origins}")
    print(f"高德地图API Key: {settings.amap_api_key}")

    # 检查LLM配置
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    llm_base_url = os.getenv("LLM_BASE_URL") or settings.llm_base_url
    llm_model = os.getenv("LLM_MODEL") or settings.llm_model

    print(f"LLM API Key: {'已配置' if llm_api_key else '未配置'}")
    print(f"LLM Base URL: {llm_base_url}")
    print(f"LLM Model: {llm_model}")
    print(f"日志级别: {settings.log_level}")
