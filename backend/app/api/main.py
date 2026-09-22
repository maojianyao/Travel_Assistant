#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : main.py
@Time    : 2026/9/21 09:22
@Author  : MaoJian Y
@Desc    : FASTAPI主应用
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import trip, poi, map as map_routers
from backend.app.config import get_settings, print_config, validate_config
from backend.app.db.trip_store import get_trip_store
from backend.app.utils.logger import get_logger


# 获取日志
logger = get_logger(__file__)
# 获取配置
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时间"""
    logger.info(f"""
    \n{'='*60}\n
    🚀 {settings.app_name} v{settings.app_version}\n
    {'='*60}\n
    """)
    print_config()

    try:
        validate_config()
        logger.info("配置验证成功")
    except Exception as e:
        logger.error(f"配置验证失败: {e}\n请检查.env文件并确保所有必要的配置项都已设置")
        raise

    # 初始化行程持久化存储(建库建表)
    get_trip_store().initialize()
    logger.info("行程持久化存储初始化完成")

    logger.info(f"""
    \n{'='*60}\n
    📚 API文档: http://localhost:8000/docs\n
    📖 ReDoc文档: http://localhost:8000/redoc\n
    {'='*60}\n
    """)

    yield

    logger.info(f"""
    \n{'='*60}\n        
    🚀 应用关闭\n        
    {'='*60}\n
    """)

# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=",",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(trip.router, prefix="/api")
app.include_router(poi.router, prefix="/api")
app.include_router(map_routers.router, prefix="/api")

@app.get("/")
async def root():
    """根目录"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )

