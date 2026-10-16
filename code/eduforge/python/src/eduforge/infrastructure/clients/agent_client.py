"""Agent 规划服务客户端。

对齐方案 §1.2 和 §6.3：
- 首版只走 local 分支（直接调用本地规划图或本地 agent_local HTTP 端点）；
- 为 Worker 和业务系统提供统一的 Agent 规划调用接口。
"""
from __future__ import annotations

import httpx

from eduforge.agent.bootstrap import build_planner
from eduforge.domain.contracts import PlannerRequest, WorkOrder
from eduforge.domain.errors import EduForgeError
from eduforge.domain.ports import AgentPlannerPort


class LocalAgentClient(AgentPlannerPort):
    """直接在进程内运行的本地规划客户端。"""

    def __init__(self, planner=None):
        self.planner = planner or build_planner()

    async def plan(self, request: PlannerRequest) -> WorkOrder:
        result = await self.planner.ainvoke({"request": request})
        return result["work_order"]


class HttpAgentClient(AgentPlannerPort):
    """通过 HTTP 访问本地或云侧 Agent 服务的客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url.rstrip("/")

    async def plan(self, request: PlannerRequest) -> WorkOrder:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/plan",
                json=request.model_dump(mode="json"),
            )
            if resp.status_code != 200:
                raise EduForgeError(
                    f"Agent 规划请求失败: status={resp.status_code}, body={resp.text}",
                    code="AGENT_REQUEST_FAILED",
                )
            return WorkOrder.model_validate(resp.json())
