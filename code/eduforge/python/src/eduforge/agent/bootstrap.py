"""智能体组装（§4.1 / §6.3）。

本地运行与 AgentArts Runtime 共用同一个 build_planner()，
不依赖本地路径、进程内状态或 Docker，以便未来平滑迁移到 AgentArts。
"""
from __future__ import annotations

from typing import Callable

from eduforge.agent.graph import build_planning_graph
from eduforge.agent.planners import ModelFn, deepseek_model
from eduforge.agent.services import PlanningServices
from eduforge.domain.contracts import PlannerRequest


def default_template_of(req: PlannerRequest) -> str:
    # 默认从 request.template_id 取（如果存在），否则使用凸透镜基础模板
    return getattr(req, "template_id", "optics.convex_lens")


def build_planner(
    model: ModelFn | None = None,
    *,
    template_of: Callable[[PlannerRequest], str] | None = None,
):
    if model is None:
        model = deepseek_model()
    resolver = template_of or default_template_of
    services = PlanningServices(model, template_of=resolver)
    return build_planning_graph(services)
