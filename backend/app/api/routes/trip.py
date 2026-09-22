#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : trip.py
@Time    : 2026/9/18 12:32
@Author  : MaoJian Y
@Desc    : 旅行规划API路由
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from backend.app.agents.trip_planner_agent import get_trip_async_planner_agent
from backend.app.db.trip_store import get_trip_store
from backend.app.models.schemas import (
    TripDetailResponse,
    TripListItem,
    TripListResponse,
    TripPlanResponse,
    TripRequest,

)

from backend.app.utils.logger import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix='/trip', tags=["旅行规划"])

def _build_success_message(plan) -> str:
    return "旅行计划生成成功" if not plan.is_fallback else "AI行程生成暂时失败, 当前返回的是示例行程, 可稍后重试"

@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求，生成详细的旅行计划",
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划
    :param request: 旅行计划请求参数
    :return: 旅行计划信息，包括景点推荐、路线建议、预算估算等
    """
    try:

        logger.info(f"""
        \n{'='*60}\n
        📥 收到旅行规划请求:\n
           城市: {request.city}\n
           日期: {request.start_date} - {request.end_date}\n
           天数: {request.travel_days}\n
        \n{'='*60}\n
        """)

        logger.info("🔄 获取多智能体系统实例...")
        # 获取agent实例
        agent = await get_trip_async_planner_agent()  # 异步执行 or 同步执行 get_trip_planner_agent
        logger.info(f"🚀 开始生成旅行计划...\n")
        plan = await agent.plan_trip(request)

        # 持久化行程并返回trip_id, 用于二次查看与分享
        trip_id = await get_trip_store().save_trip_async(request.model_dump(), plan.model_dump())

        logger.info(f"✅ 旅行计划生成成功,准备返回响应\n")
        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=plan,
            trip_id=trip_id
        )
    except Exception as e:
        logger.error(f"旅行计划生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"旅行计划生成失败：{str(e)}")

@router.post(
    "/plan/stream",
    summary="流式生成旅行计划(SSE)",
    description="通过SSE实时推送各智能体执行进度, 最终事件携带完整旅行计划",
)
async def plan_trip_stream(request: TripRequest):
    """
    流式生成旅行计划
    :param request: 旅行计划请求参数
    :return: text/event-stream, 事件格式: data: {"type": "progress"|"result"|"error", ...}
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def progress_callback(stage: str, percent: int, message: str):
        await queue.put({"type": "progress", "stage": stage, "percent": percent, "message": message})

    async def run_planner():
        try:
            agent = await get_trip_async_planner_agent()
            plan = await agent.plan_trip(request, progress_callback=progress_callback)
            trip_id = await get_trip_store().save_trip_async(request.model_dump(), plan.model_dump())
            await queue.put({
                "type": "result",
                "success": True,
                "message": _build_success_message(plan),
                "trip_id": trip_id,
                "data": plan.model_dump(),
            })
        except Exception as e:
            logger.error(f"流式生成旅行计划失败: {e}")
            import traceback
            traceback.print_exc()
            await queue.put({"type": "error", "success": False, "message": f"旅行计划生成失败：{str(e)}"})

    task = asyncio.create_task(run_planner())

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("result", "error"):
                    break
        except asyncio.CancelledError:
            raise
        finally:
            # 客户端断开时终止后台生成任务, 避免资源浪费
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/list",
    response_model=TripListResponse,
    summary="获取行程历史列表",
    description="按创建时间倒序返回最近的行程记录",
)
async def list_trips(limit: int = 20):
    try:
        trips = await get_trip_store().list_trips_async(limit)
        items = [TripListItem(**item) for item in trips]
        return TripListResponse(success=True, message="行程列表获取成功", data=items)
    except Exception as e:
        logger.error(f"行程列表获取失败: {e}")
        raise HTTPException(status_code=500, detail=f"行程列表获取失败: {str(e)}")


@router.get(
    "/detail/{trip_id}",
    response_model=TripDetailResponse,
    summary="按ID获取行程详情",
    description="用于行程二次查看与分享链接访问",
)
async def get_trip_detail(trip_id: str):
    try:
        record = await get_trip_store().get_trip_async(trip_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"行程不存在: {trip_id}")
        return TripDetailResponse(
            success=True,
            message="行程详情获取成功",
            trip_id=record["trip_id"],
            created_at=record["created_at"],
            data=record["plan"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"行程详情获取失败: {e}")
        raise HTTPException(status_code=500, detail=f"行程详情获取失败: {str(e)}")


@router.get(
    "/health",
    summary="检查服务健康状态",
    description="检查旅行规划服务的健康状态，确保服务正常运行"
)
async def health_check():
    """健康检查"""
    try:
        # 检查agent是否可用,高德地图api服务是否可用
        agent = await get_trip_async_planner_agent()
        tools = await agent.list_tools()
        return {
            "status": "healthy",
            "service": "trip-planner",
            "tools_count": len(tools)
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=503, detail=f"服务不可用：{str(e)}")
