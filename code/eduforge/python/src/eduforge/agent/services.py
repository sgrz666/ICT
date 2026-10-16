"""规划图的节点实现。

模型只产 EditProposal；模板清单提供量程与视图，策略层决定能不能做。
`model` 是个可调用对象（真 DeepSeek 或测试桩），这样无 API Key 也能整条验。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from eduforge.agent.policy import Rejected, authorize, load_template
from eduforge.domain.contracts import EditProposal, PlannerRequest, WorkOrder
from eduforge.validation.reports import ValidationReport

ModelFn = Callable[[str, dict[str, Any], list[dict[str, Any]]], Awaitable[dict[str, Any]]]


class PlanningServices:
    def __init__(self, model: ModelFn, *, template_of: Callable[[PlannerRequest], str]):
        self.model = model
        self.template_of = template_of

    async def load_context(self, request: PlannerRequest) -> dict[str, Any]:
        template_id = self.template_of(request)
        spec = load_template(template_id)
        return {
            "template_id": template_id,
            "spec": spec,
            "base_revision": str(request.base_revision),
        }

    async def retrieve(self, prompt: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        """首版是小型本地知识集：把清单里的控件与视图原样交给模型。

        检索结果只能提供事实，不能扩大权限——权限由 policy.authorize 判。
        """
        spec = context["spec"]
        evidence: list[dict[str, Any]] = []
        for c in spec.controls:
            evidence.append({
                "kind": "control",
                "entity_id": c.entity_id,
                "parameter": c.parameter,
                "min": c.min,
                "max": c.max,
            })
        for v in spec.views:
            evidence.append({"kind": "view", "view_id": v})
        return evidence

    async def draft(self, request, context, evidence) -> EditProposal:
        raw = await self.model(request.prompt, context, evidence)
        # 模型输出必须过我们自己的结构校验，不接受"看起来像"的字典
        return EditProposal.model_validate(raw)

    def authorize(self, request, context, proposal) -> WorkOrder:
        return authorize(request, context["spec"], proposal)
