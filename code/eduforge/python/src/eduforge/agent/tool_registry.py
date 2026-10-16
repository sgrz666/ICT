"""主 Agent 可见的工具集：窄集合 + 把失败变成可观察的返回。

两条纪律：

1. **发布与构建不进模型可见集**。`build_package` / `publish_revision` 由后端在
   四道闸门事务里执行（`application/publication.py` → `JobRepository.publish`）。
   模型能自述「已发布」，就不能由它来判定「可以发布」。
2. **工具失败必须成为观察，而不是中断循环**。策略拒绝、引擎拒绝、并发冲突都是
   模型下一步要读的东西；让它抛穿到 ainvoke，循环就只剩「崩了」这一种结局，
   而我们要的是「看到失败并据此修」。
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

from langchain_core.tools import StructuredTool

from eduforge.agent.policy import Rejected
from eduforge.domain.errors import EduForgeError
from eduforge.experiment_tools.langchain_tools import get_experiment_tools
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.db.repositories import RevisionConflict

# 模型可见的工具名。写死成常量，便于用测试钉住「发布类工具不在这里」。
AGENT_VISIBLE_TOOLS = (
    "search_experiments",
    "open_experiment",
    "inspect_scene",
    "apply_scene_patch",
    "configure_teaching_views",
    "run_validation",
)

BACKEND_ONLY_TOOLS = ("build_package", "publish_revision")


def _as_observation(fn: Callable[..., Coroutine[Any, Any, dict]]) -> Callable[..., Coroutine[Any, Any, dict]]:
    """把领域异常转成结构化返回，让模型读得懂「为什么这次没成」。"""

    async def wrapped(**kwargs: Any) -> dict[str, Any]:
        try:
            return await fn(**kwargs)
        except (EduForgeError, RevisionConflict, Rejected) as exc:
            # `Rejected` 是策略层的拒绝，不是 EduForgeError 的子类；漏接它
            # 会让越界参数直接打穿循环——「失败成为观察」这条纪律就只剩一半。
            code = getattr(exc, "code", None) or getattr(exc, "reason", None) or type(exc).__name__
            return {
                "isError": True,
                "code": code,
                "detail": str(exc),
                "next_step": "读这条失败原因再决定怎么改，不要重复同一个动作，也不要换值蒙混。",
            }

    return wrapped


def agent_tools(service: ExperimentToolService) -> list[StructuredTool]:
    """返回主 Agent 可自主调用的工具（6 项），并包装其失败观察。"""
    wrapped: list[StructuredTool] = []
    for tool in get_experiment_tools(service):
        if tool.name not in AGENT_VISIBLE_TOOLS:
            continue
        tool.coroutine = _as_observation(tool.coroutine)
        wrapped.append(tool)
    return wrapped
