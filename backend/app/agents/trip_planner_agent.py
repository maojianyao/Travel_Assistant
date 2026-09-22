#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : trip_planner_agent.py
@Time    : 2026/9/18 21:30
@Author  : MaoJian Y
@Desc    : 多智能体旅行规划系统
"""
import asyncio
import json
import re
from typing import Optional, Callable, Awaitable

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from backend.app.config import get_settings
from backend.app.models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Location, Meal
from backend.app.services.amap_service import get_amap_service
from backend.app.services.llm_service import get_llm
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
你必须使用工具来搜索景点!不要自己编造景点信息!

**回答要求:**
- 必须使用工具,不要直接回答
- 根据工具返回的结果，筛选出符合用户偏好的景点。
- 列出景点名称、地址、评分、类型等关键信息，并简要说明推荐理由。
- 如果搜索结果为空，告知用户未找到，并建议更换关键词或扩大搜索范围。
- 用中文回答，语言友好、简洁。
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
你必须使用工具来查询天气!不要自己编造天气信息!

**回答要求:**
- 必须使用工具,不要直接回答
- 根据工具返回的结果，提取并展示城市的天气状况、温度、风力、湿度等关键信息。
- 如果查询的是未来天气，请说明日期和对应的天气情况。
- 如果工具返回错误或未找到城市，告知用户查询失败，并建议检查城市名称是否正确。
- 用中文回答，语言友好、简洁。
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
你必须使用工具来搜索酒店!不要自己编造酒店信息!

**回答要求:**
- 必须使用工具,不要直接回答
- 根据工具返回的结果，筛选出符合用户需求的酒店。
- 列出酒店名称、地址、评分、参考价格（如有）、距离景点距离、类型等关键信息，并简要说明推荐理由。
- 如果搜索结果为空，告知用户未找到，并建议更换关键词或扩大搜索范围。
- 用中文回答，语言友好、简洁。
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. 你不需要调用任何工具,只需汇总下方提供的信息进行规划
2. weather_info数组必须包含每一天的天气信息
3. 温度必须是纯数字(不要带°C等单位)
4. 每天安排2-3个景点
5. 考虑景点之间的距离和游览时间
6. 每天必须包含早中晚三餐
7. 提供实用的旅行建议
8. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
9. 只返回JSON数据,不要返回其他内容
"""


amap_service = get_amap_service()

# 进度回调类型: (阶段, 百分比0-100, 提示信息)
ProgressCallback = Callable[[str, int, str], Awaitable[None]]

@tool("search_weather")
def get_weather_tool(city: str):
    """
    查询天气信息
    :param
    city: 城市
    :return: 天气信息列表
    """
    return amap_service.get_weather(city)

@tool("search_poi")
def search_poi_tool(keywords: str, city: str, citylimit: bool=True):
    """
    根据关键词和城市搜索POI信息
    :param keywords: 搜索关键词
    :param city: 城市
    :param citylimit: 是否限制城市范围内
    :return: POI信息列表
    """
    return amap_service.search_poi(keywords, city, citylimit)

@tool("get_poi_detail")
def get_poi_detail_tool(poi_id: str):
    """
    根据POI ID获取POI详情
    :param poi_id: POI ID
    :return: POI详情
    """
    return amap_service.get_poi_detail(poi_id)


@tool("plan_route")
def plan_route_tool(origin_address: str,
               destination_address: str,
               origin_city: Optional[str] = None,
               destination_city: Optional[str] = None,
               route_type: str = 'walking'):
    """
    规划路线
    :param origin_address: 起点地址
    :param destination_address: 终点地址
    :param origin_city: 起点城市
    :param destination_city: 终点城市
    :param route_type: 路线类型（'walking'、'driving'、'transit'）
    :return: 路线信息
    """
    return amap_service.plan_route(origin_address, destination_address, origin_city, destination_city, route_type)


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""
    _tools: list[tool] = [get_weather_tool, search_poi_tool, get_poi_detail_tool, plan_route_tool]
    def __init__(self):
        logger.info("初始化多智能体旅行规划系统")

        try:
            self.llm = get_llm()

            # 创建景点搜索智能体
            self.attraction_agent = create_agent(
                model=self.llm,
                tools=self._tools,
                system_prompt=ATTRACTION_AGENT_PROMPT
            )
            logger.info("景点搜索智能体初始化完成")

            # 创建天气智能体
            self.weather_agent = create_agent(
                model=self.llm,
                tools=self._tools,
                system_prompt=WEATHER_AGENT_PROMPT
            )
            logger.info("天气智能体初始化完成")

            # 创建酒店推荐智能体
            self.hotel_agent = create_agent(
                model=self.llm,
                tools=self._tools,
                system_prompt=HOTEL_AGENT_PROMPT
            )
            logger.info("酒店推荐智能体初始化完成")

            # 创建行程规划智能体
            self.planner_agent = create_agent(
                model=self.llm,
                tools=[],
                system_prompt=PLANNER_AGENT_PROMPT
            )
            logger.info("行程规划智能体初始化完成")
            logger.info("多智能体系统初始化成功")
        except Exception as e:
            logger.error(f"多智能体系统初始化出错: {e}")
            import traceback
            traceback.print_exc()
            raise

    def plan_trip(self, request: TripRequest) -> TripPlan:
        """
        使用多智能体协作生成旅行计划
        :param request: 旅行计划请求参数
        :return: 旅行计划
        """
        try:
            logger.info(f"""
            \n{'='*60}\n\n
            🚀 开始多智能体协作规划旅行...\n
            目的地：{request.city}\n
            日期：{request.start_date} 至 {request.end_date}\n
            天数：{request.travel_days}\n
            偏好：{','.join(request.preferences) if request.preferences else '无'}\n\n
            {'='*60}\n
            """)

            # 步骤1:景点搜索Agent搜索景点
            query = self._build_attraction_query(request)
            attraction_response = self.attraction_agent.invoke({"messages": f"{query}"})
            attraction_result = attraction_response['messages'][-1].content
            logger.info(f"景点搜索结果: {attraction_result[:200] +'...' if len(attraction_result) > 200 else attraction_result}\n")

            # 步骤2:天气查询Agent查询天气
            weather_response = self.weather_agent.invoke({"messages": f"请查询{request.city}的天气"})
            weather_result = weather_response['messages'][-1].content
            logger.info(f"天气查询结果: {weather_result[:200] +'...' if len(weather_result) > 200 else weather_result}\n")

            # 步骤3:酒店推荐Agent推荐酒店
            hotel_response = self.hotel_agent.invoke({"messages": f"请推荐{request.city}的{request.accommodation}酒店"})
            hotel_result = hotel_response['messages'][-1].content
            logger.info(f"酒店推荐结果: {hotel_result[:200] +'...' if len(hotel_result) > 200 else hotel_result}\n")

            # 步骤4:行程规划Agent规划行程
            planner_query = self._build_planner_query(request, attraction_result, weather_result, hotel_result)
            planner_response = self.planner_agent.invoke({"messages": f"{planner_query}"})
            planner_result = planner_response['messages'][-1].content
            logger.info(f"行程规划结果: {planner_result[:500] +'...' if len(planner_result) > 500 else planner_result}\n")

            trip_plan = self._parse_response(planner_result, request)
            return trip_plan
        except Exception as e:
            logger.error(f"旅行计划请求参数解析出错: {e}")
            import traceback
            traceback.print_exc()
            return self._create_fallback_plan(request)

    def _build_attraction_query(self, request: TripRequest) -> str:
        keywords = []
        if request.preferences:
            keywords.extend(f"{request.preferences}")
        else:
            keywords.append("景点")
        query = f"请使用search_poi工具搜索{request.city}的相关{' '.join(keywords)}"
        return query

    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
        """
        构建行程规划查询
        :param request: 旅行计划请求参数
        :param attractions: 景点信息
        :param weathers: 天气信息
        :param hotels: 酒店信息
        :return: 行程规划查询
        """
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划：
**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确
"""
        return query

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应
        :param response: Agent响应文本
        :param request: 旅行计划请求参数
        :return: 解析后的旅行计划
        """
        try:
            # 尝试从响应中提取JSON，查找JSON代码块
            if "```json" in response:
                json_code_block = re.search(r'```json(.*?)```', response, re.DOTALL)
                json_str = json_code_block.group(1)
            elif "```" in response:
                json_code_block = re.search(r'```(.*?)```', response, re.DOTALL)
                json_str = json_code_block.group(1)
            elif "{" in response and "}" in response:
                json_str = re.search(r'({.*})', response, re.DOTALL).group(1)
            else:
                raise ValueError("No JSON found in response")

            # 解析JSON
            data = json.loads(json_str)
            trip_plan = TripPlan(**data)
            return trip_plan
        except Exception as e:
            logger.error(f"⚠️  旅行计划响应解析出错: {e}")
            logger.info(f"   将使用备用方案生产计划")
            return self._create_fallback_plan(request)

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """
        创建备用计划（当Agent失败时）
        :param request: 旅行计划请求参数
        :return: 备用计划
        """
        from datetime import datetime, timedelta

        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name = f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(
                        type="breakfast",
                        name=f"第{i+1}天早餐",
                        description="当地特色早餐"
                    ),
                    Meal(
                        type="lunch",
                        name=f"第{i+1}天午餐",
                        description="午餐推荐"
                    ),
                    Meal(
                        type="dinner",
                        name=f"第{i+1}天晚餐",
                        description="晚餐推荐"
                    )
                ]
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}天旅行计划，建议提前查看各景点的开放时间"

        )

# 全局多智能体系统实例
_multi_agent_planner = None

def get_trip_planner_agent() -> MultiAgentTripPlanner:
    global _multi_agent_planner
    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()
    return _multi_agent_planner


class MultiAgentAsyncTripPlanner:
    """基于MCP服务的多智能体异步旅行规划系统
    架构说明：
    - 通过MultiServerMCPClient连接高德地图MCP服务，动态加载地图工具
    - 景点搜索/天气查询/酒店推荐三个智能体基于MCP工具异步并发执行
    - 行程规划智能体汇总三个智能体的结果，总结输出最终旅行计划
    """
    _AMAP_MCP_SERVER_NAME = "amap"
    _AMAP_MCP_SSE_URL = "https://mcp.amap.com/sse"
    def __init__(self):
        self.llm = None
        self._tools: list = []
        self._initialized: bool = False

        self.attraction_agent = None
        self.weather_agent = None
        self.hotel_agent = None
        self.planner_agent = None

    async def initialize(self) -> "MultiAgentAsyncTripPlanner":
        """初始化MCP客户端并创建各智能体(幂等, 可重复调用)"""
        if self._initialized:
            return self

        logger.info("初始化多智能体旅行规划系统(MCP模式)")
        try:
            settings = get_settings()
            if not settings.amap_api_key:
                raise ValueError("AMAP_API_KEY未配置, 无法连接高德MCP服务")

            self.llm = get_llm()

            # 连接MCP服务并加载高德地图工具
            self._mcp_client = MultiServerMCPClient({
                self._AMAP_MCP_SERVER_NAME: {
                    "url": f"{self._AMAP_MCP_SSE_URL}?key={settings.amap_api_key}",
                    "transport": "sse",
                }
            })
            self._tools = await self._mcp_client.get_tools()
            logger.info(f"MCP服务连接成功, 共加载{len(self._tools)}个工具")

            # 创建景点搜索智能体
            self.attraction_agent = create_agent(
                model=self.llm,
                tools=self._tools,
                system_prompt=ATTRACTION_AGENT_PROMPT
            )
            logger.info("景点搜索智能体初始化完成")

            # 创建天气查询智能体
            self.weather_agent = create_agent(
                model=self.llm,
                tools=self._tools,
                system_prompt=WEATHER_AGENT_PROMPT
            )
            logger.info("天气查询智能体初始化完成")

            # 创建酒店推荐智能体
            self.hotel_agent = create_agent(
                model=self.llm,
                tools=self._tools,
                system_prompt=HOTEL_AGENT_PROMPT
            )
            logger.info("酒店推荐智能体初始化完成")

            # 创建行程规划智能体(仅汇总信息, 不需要工具)
            self.planner_agent = create_agent(
                model=self.llm,
                tools=[],
                system_prompt=PLANNER_AGENT_PROMPT
            )
            logger.info("行程规划智能体初始化完成")

            self._initialized = True
            logger.info("多智能体系统初始化成功")
            return self
        except Exception as e:
            logger.error(f"多智能体系统初始化出错: {e}")
            import traceback
            traceback.print_exc()
            raise
    # 行程结构化输出最大重试次数
    _PLANNER_MAX_RETRIES = 3
    async def plan_trip(self, request: TripRequest, progress_callback: Optional[ProgressCallback] = None) -> TripPlan:
        """
        使用多智能体协作生成旅行计划
        :param request: 旅行计划请求参数
        :param progress_callback: 进度回调, 用于SSE实时推送生成进度
        :return: 旅行计划
        """
        await self.initialize()

        async def report(stage: str, percent: int, message: str):
            if progress_callback is None:
                return
            try:
                await progress_callback(stage, percent, message)
            except Exception as e:
                logger.warning(f"进度回调执行失败: {e}")

        try:
            logger.info(f"""
            \n{'=' * 60}\n\n
            🚀 开始多智能体协作规划旅行...\n
            目的地：{request.city}\n
            日期：{request.start_date} 至 {request.end_date}\n
            天数：{request.travel_days}\n
            偏好：{','.join(request.preferences) if request.preferences else '无'}\n
            {'=' * 60}\n
            """)

            await report("init", 10, "🤖 智能体就绪, 开始采集景点/天气/酒店信息")

            # 步骤1-3: 景点搜索/天气查询/酒店推荐三个智能体异步并发执行
            results = await asyncio.gather(
                self._run_agent(self.attraction_agent, self._build_attraction_query(request)),
                self._run_agent(self.weather_agent, self._build_weather_query(request)),
                self._run_agent(self.hotel_agent, self._build_hotel_query(request)),
                return_exceptions=True,
            )

            attraction_result = self._resolve_agent_result(results[0], "景点搜索", f"{request.city}景点信息暂不可用")
            weather_result = self._resolve_agent_result(results[1], "天气查询", f"{request.city}天气信息暂不可用")
            hotel_result = self._resolve_agent_result(results[2], "酒店推荐", f"{request.city}酒店信息暂不可用")

            await report("collected", 55, "✅ 信息采集完成, 正在规划每日行程")

            # 步骤4: 行程规划智能体汇总所有信息并总结输出最终计划
            planner_query = self._build_planner_query(request, attraction_result, weather_result, hotel_result)

            planner_result = await self._run_agent(self.planner_agent, planner_query)
            trip_plan = self._parse_response(planner_result, request)

            await report("locating", 90, "📍 正在通过高德POI校验景点坐标")
            # 步骤5: 用高德POI真实坐标回填, 避免LLM编造坐标导致地图标点偏移
            fixed_count = await self._fill_real_locations(trip_plan)

            await report("done", 100, f"🎉 规划完成, 已校验{fixed_count}个景点坐标")
            return trip_plan

        except Exception as e:
            logger.error(f"旅行计划生成出错: {e}")
            import traceback
            traceback.print_exc()
            return self._create_fallback_plan(request)

    @staticmethod
    async def _run_agent(agent, message: str) -> str:
        """
        调用单个智能体并返回其最终回复文本
        :param agent: 智能体实例
        :param message: 发送给智能体的消息
        :return: 智能体最终回复文本
        """
        response = await agent.ainvoke({"messages": message})
        content = response["messages"][-1].content
        return content if isinstance(content, str) else str(content)

    @staticmethod
    def _resolve_agent_result(result, agent_name: str, fallback: str) -> str:
        """
        处理单个智能体的执行结果, 失败时降级为提示信息, 不阻断整体流程
        :param result: 智能体执行结果或异常
        :param agent_name: 智能体名称
        :param fallback: 降级提示信息
        :return: 结果文本
        """
        if isinstance(result, Exception):
            logger.error(f"{agent_name}智能体执行失败: {result}")
            return fallback
        logger.info(f"{agent_name}结果: {result[:200] + '...' if len(result) > 200 else result}\n")
        return result

    async def _fill_real_locations(self, trip_plan: TripPlan) -> int:
        """
        用高德POI搜索结果回填景点真实坐标, 避免LLM编造经纬度导致地图标点偏移
        :param trip_plan: 旅行计划
        :return: 成功回填的景点数量
        """
        fixed_count = 0

        async def fill_one(attraction: Attraction):
            nonlocal fixed_count
            try:
                pois = await asyncio.to_thread(amap_service.search_poi, attraction.name, trip_plan.city)
                if pois:
                    attraction.location = pois[0].location
                    if not attraction.address:
                        attraction.address = pois[0].address
                    fixed_count += 1
                else:
                    logger.warning(f"坐标回填未找到POI, 保留LLM结果: {attraction.name}")
            except Exception as e:
                logger.warning(f"坐标回填失败, 保留LLM结果: {attraction.name}: {e}")

        for day in trip_plan.days:
            await asyncio.gather(*(fill_one(attraction) for attraction in day.attractions))
        logger.info(f"景点坐标回填完成: {fixed_count}个景点已使用高德POI真实坐标")
        return fixed_count

    def _build_attraction_query(self, request: TripRequest) -> str:
        """
        构建景点搜索查询
        :param request: 旅行计划请求参数
        :return: 景点搜索查询
        """
        keywords = " ".join(request.preferences) if request.preferences else "景点"
        query = f"请搜索{request.city}的'{keywords}'相关景点, 列出景点名称、地址、评分、经纬度坐标、门票价格等关键信息"
        if request.free_text_input:
            query += f"。用户额外要求: {request.free_text_input}"
        return query

    def _build_weather_query(self, request: TripRequest) -> str:
        """
        构建天气查询请求
        :param request: 旅行计划请求参数
        :return: 天气查询请求
        """
        return f"请查询{request.city}未来{request.travel_days}天的天气预报, 包含日期、白天/夜间天气、温度、风向风力等信息"

    def _build_hotel_query(self, request: TripRequest) -> str:
        """
        构建酒店推荐请求
        :param request: 旅行计划请求参数
        :return: 酒店推荐请求
        """
        return f"请搜索{request.city}的{request.accommodation}, 列出酒店名称、地址、评分、价格、经纬度坐标等关键信息"

    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
        """
        构建行程规划查询
        :param request: 旅行计划请求参数
        :param attractions: 景点信息
        :param weather: 天气信息
        :param hotels: 酒店信息
        :return: 行程规划查询
        """
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划：
    **基本信息:**
    - 城市: {request.city}
    - 日期: {request.start_date} 至 {request.end_date}
    - 天数: {request.travel_days}天
    - 交通方式: {request.transportation}
    - 住宿: {request.accommodation}
    - 偏好: {', '.join(request.preferences) if request.preferences else '无'}

    **景点信息:**
    {attractions}

    **天气信息:**
    {weather}

    **酒店信息:**
    {hotels}

    **要求:**
    1. 每天安排2-3个景点
    2. 每天必须包含早中晚三餐
    3. 每天从酒店信息中选择一个具体的酒店
    4. 考虑景点之间的距离和交通方式
    5. 返回完整的JSON格式数据
    6. 景点的经纬度坐标要真实准确
    """
        return query

    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应
        :param response: Agent响应文本
        :param request: 旅行计划请求参数
        :return: 解析后的旅行计划
        """
        try:
            # 尝试从响应中提取JSON，查找JSON代码块
            if "```json" in response:
                json_code_block = re.search(r'```json(.*?)```', response, re.DOTALL)
                json_str = json_code_block.group(1)
            elif "```" in response:
                json_code_block = re.search(r'```(.*?)```', response, re.DOTALL)
                json_str = json_code_block.group(1)
            elif "{" in response and "}" in response:
                json_str = re.search(r'({.*})', response, re.DOTALL).group(1)
            else:
                raise ValueError("No JSON found in response")

            # 解析JSON
            data = json.loads(json_str)
            trip_plan = TripPlan(**data)
            return trip_plan
        except Exception as e:
            logger.error(f"⚠️  旅行计划响应解析出错: {e}")
            logger.info(f"   将使用备用方案生产计划")
            return self._create_fallback_plan(request)

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """
        创建备用计划（当Agent失败时）
        :param request: 旅行计划请求参数
        :return: 备用计划
        """
        from datetime import datetime, timedelta

        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name = f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(
                        type="breakfast",
                        name=f"第{i+1}天早餐",
                        description="当地特色早餐"
                    ),
                    Meal(
                        type="lunch",
                        name=f"第{i+1}天午餐",
                        description="午餐推荐"
                    ),
                    Meal(
                        type="dinner",
                        name=f"第{i+1}天晚餐",
                        description="晚餐推荐"
                    )
                ]
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}天旅行计划，建议提前查看各景点的开放时间",
            is_fallback=True
        )
    async def list_tools(self):
        if self._initialized:
            return self._tools
        await self.initialize()
        return self._tools

_multi_agent_async_planner: Optional[MultiAgentAsyncTripPlanner] = None
async def get_trip_async_planner_agent() -> MultiAgentAsyncTripPlanner:
    """获取全局多智能体系统实例(单例, 首次调用时完成MCP连接与初始化)"""
    global _multi_agent_async_planner
    if _multi_agent_async_planner is None:
        _multi_agent_async_planner = MultiAgentAsyncTripPlanner()
        await _multi_agent_async_planner.initialize()
    return _multi_agent_async_planner


async def main_async():
    """本地调试入口: 通过MCP多智能体系统生成旅行计划"""
    planner = await get_trip_async_planner_agent()
    request = TripRequest(
        city="长沙",
        start_date="2026-09-25",
        end_date="2026-09-27",
        travel_days=3,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=["历史文化", "美食"], )
    trip_plan = await planner.plan_trip(request)
    print(trip_plan.model_dump_json(indent=2))


def main():
    """本地调试入口: 通过多智能体系统调用API接口生成旅行计划"""
    planner = get_trip_planner_agent()
    request = TripRequest(
        city="长沙",
        start_date="2026-09-25",
        end_date="2026-09-27",
        travel_days=3,
        transportation="公共交通",
        accommodation="经济型酒店",
        preferences=["历史文化", "美食"], )
    trip_plan = planner.plan_trip(request)
    print(trip_plan.model_dump_json(indent=2))

if __name__ == '__main__':
    asyncio.run(main_async())
    main()
