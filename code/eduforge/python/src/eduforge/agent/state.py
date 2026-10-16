"""LangGraph 规划状态与服务接口。

对齐方案 §1.2 和 §4.2。
"""
from __future__ import annotations

from typing import Any, Protocol, TypedDict

from eduforge.domain.contracts import EditProposal, PlannerRequest, WorkOrder


class PlanningState(TypedDict, total=False):
    """LangGraph 规划状态机数据字典。"""
    request: PlannerRequest
    context: dict[str, Any]
    evidence: list[dict[str, Any]]
    proposal: EditProposal
    work_order: WorkOrder


class PlanningServices(Protocol):
    """规划服务抽象接口。"""

    async def load_context(self, request: PlannerRequest) -> dict[str, Any]:
        """读取指定基础版本，加载可信模板及能力清单。"""
        ...

    async def retrieve(self, prompt: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        """获取相关参数、接口、教学依据和错误说明。"""
        ...

    async def draft(
        self,
        request: PlannerRequest,
        context: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> EditProposal:
        """请求模型生成 EditProposal，执行 Pydantic 校验。"""
        ...

    def authorize(
        self,
        request: PlannerRequest,
        context: dict[str, Any],
        proposal: EditProposal,
    ) -> WorkOrder:
        """校验对象、参数、范围、视图、代码修改范围，构造工作单。"""
        ...
