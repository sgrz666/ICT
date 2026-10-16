"""Deep Agents 作为 `PlannerPort` 的生产实现。

分工决定了「一个执行核心」这句话怎么落地：

- **模型负责决定**：读哪个实验、改哪个参数、验证失败后要不要再改；
- **管线负责提交**：`Chain.planning` 仍会把这里返回的 `EditProposal` 交给
  `policy.authorize()`，后续 editing/building/validating/packaging 与四道闸门
  发布事务一律照旧执行。模型看不到、也调不到 `build_package` / `publish_revision`。

返回的提案不是模型自述的一段 JSON，而是**从它实际成功的工具调用里派生**的：
只有真的被引擎接受、真的落进场景的编辑才会成为操作。它说改了什么不算数，
观察到的才算数。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import asyncpg

from eduforge.agent.deepagents_runtime import run_experiment_agent
from eduforge.agent.model import create_model
from eduforge.agent.policy import Rejected
from eduforge.domain.contracts import EditProposal, PlannerRequest, SetParameter, SetView
from eduforge.experiment_tools.contracts import JobContext, OpenExperimentInput
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient


def operations_from_trace(trace: list[dict[str, Any]]) -> list[SetParameter | SetView]:
    """把「成功的工具调用」折算成提案操作。"""
    ops: list[SetParameter | SetView] = []
    for step in trace:
        if step.get("is_error"):
            continue
        args = step.get("args") or {}
        if step["tool_name"] == "apply_scene_patch":
            edits = args.get("edits") or []
            if isinstance(edits, dict):
                edits = [edits]
            for e in edits:
                ops.append(SetParameter(
                    entity_id=str(e["entity_id"]), parameter=str(e["parameter"]), value=float(e["value"])
                ))
        elif step["tool_name"] == "configure_teaching_views":
            views = args.get("views") or {}
            if isinstance(views, list):
                views = {str(v.get("view_id") or v.get("id")): bool(v.get("visible", True)) for v in views}
            for vid, visible in views.items():
                ops.append(SetView(view_id=str(vid), visible=bool(visible)))
    return ops


@dataclass
class DeepAgentPlanner:
    """PlannerPort：让 Deep Agents 在真实实验上跑一轮，再把成果折算成提案。"""

    conn: asyncpg.Connection
    engine: EngineClient
    artifact_dir: Path
    max_turns: int = 30
    model_factory: Callable[..., Any] = create_model

    async def plan(self, request: PlannerRequest) -> EditProposal:
        row = await self.conn.fetchrow(
            "select owner_id, lease_token from jobs where id = $1", request.job_id
        )
        if row is None:
            raise Rejected("JOB_NOT_FOUND", str(request.job_id))

        # 作用域由 job 决定：实验、基础版本、归属、租约，模型一律改不了
        job = JobContext(
            job_id=request.job_id,
            owner_id=row["owner_id"],
            lease_token=row["lease_token"] or "",
            experiment_id=request.experiment_id,
            base_revision=request.base_revision,
        )
        service = ExperimentToolService(
            engine_client=self.engine, conn=self.conn,
            artifact_dir=self.artifact_dir, job=job,
        )
        # 由服务端把 job 的目标实验装进工作态：不是让模型去猜该怎么打开，
        # 也保证它之后只能看到这个实验（作用域已在 JobContext 里钉死）。
        await service.open_experiment(
            OpenExperimentInput(
                experiment_id=str(request.experiment_id),
                template_id=request.template_id,
                revision_id=str(request.base_revision),
            )
        )

        out = await run_experiment_agent(
            model=self.model_factory(temperature=0),
            service=service,
            prompt=request.prompt,
            job_id=str(request.job_id),
            max_turns=self.max_turns,
            extra_facts=(
                f"目标实验 {request.experiment_id}，基础版本 {request.base_revision}，"
                f"模板 {request.template_id}。"
            ),
        )

        ops = operations_from_trace(out["trace"])
        if not ops:
            # 一次有效修改都没有，就不能交出一份「看起来完成了」的提案
            raise Rejected(
                "NO_EFFECTIVE_OPERATIONS",
                f"模型共发起 {out['tool_calls_total']} 次调用，没有一次形成被引擎接受的修改",
            )
        return EditProposal(route="config", operations=ops)
