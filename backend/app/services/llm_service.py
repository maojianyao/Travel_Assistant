#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : llm_service.py
@Time    : 2026/9/18 15:05
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""
import os

from langchain_openai import ChatOpenAI

from backend.app.config import get_settings

_llm_instance = None


def get_llm() -> ChatOpenAI:
    """获取LLM实例"""
    global _llm_instance

    if not _llm_instance:
        settings = get_settings()
        _llm_instance = ChatOpenAI(
            api_key=settings.llm_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=settings.llm_base_url or os.getenv("OPENAI_BASE_URL"),
            model=settings.llm_model or os.getenv("OPENAI_MODEL") or "gpt-5.6",
            extra_body={"thinking": {"type": "disabled"}},
        )
        return _llm_instance

    return _llm_instance


def reset_llm():
    """重置LLM实例（用于测试或重新配置）"""
    global _llm_instance
    _llm_instance = None

