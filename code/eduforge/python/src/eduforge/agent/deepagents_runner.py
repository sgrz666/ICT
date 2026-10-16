"""Deep Agents 的生产执行端口：跑完一轮交回**候选完成记录**，而不是操作清单。

与 `DeepAgentPlanner` 的差别只有一句话：

- Planner 把模型成功的调用折算成 `EditProposal`，Worker 再在基线上重放一遍。
  于是模型验的那份场景和发布出去的那份是两个对象，`operations_from_trace`
  实际上成了业务状态源。
- Runner 让模型通过同一套工具直接改库里的候选，Worker 之后只消费这份候选。
  Trace 回到它该在的位置：审计台账。

`terminal_state` 全部由候选行与验证报告算出，不看模型自述了些什么。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import asyncpg

from eduforge.agent.deepagents_runtime import run_experiment_agent
from eduforge.agent.model import create_model
from eduforge.agent.policy import Rejected
from eduforge.application.candidate_service import AgentRunRecord
from eduforge.domain.contracts import PlannerRequest
from eduforge.experiment_tools.contracts import JobContext, OpenExperimentInput
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient


async def finish_run(
    conn: asyncpg.Connection,
    *,
    service: ExperimentToolService,
    baseline_version: int,
    profile: str,
    trace: dict[str, Any] | None = None,
    tool_calls_total: int = 0,
) -> AgentRunRecord:
    """由候选行与验证报告算出执行记录——两个 Runner 共用这一条判定。"""
    state = await service.candidates.load()
    if state is None:
        raise Rejected("CANDIDATE_MISSING", str(service.job.job_id if service.job else "?"))

    if trace is not None:
        # 台账落库只作审计；它不参与「能不能发布」的判定
        await service.candidates.attach_trace(trace)

    verdict: str | None = None
    if state.validation_id is not None:
        verdict = await conn.fetchval(
            "select verdict from validation_reports where id = $1", state.validation_id
        )

    if state.state_version <= baseline_version:
        raise Rejected(
            "NO_EFFECTIVE_OPERATIONS",
            f"模型共发起 {tool_calls_total} 次调用，没有一次形成写进候选的修改",
        )
    if verdict == "passed" and state.is_validated:
        terminal = "candidate_ready"
    elif state.validation_id is not None:
        terminal = "validation_failed"
    else:
        terminal = "candidate_unvalidated"

    return AgentRunRecord(
        candidate_id=state.candidate_id,
        content_hash=state.content_hash,
        state_version=state.state_version,
        validation_id=state.validation_id,
        validation_verdict=verdict,
        agent_trace_ref=f"experiment_candidates.agent_trace:{state.candidate_id}",
        terminal_state=terminal,
        tool_calls_total=tool_calls_total,
        model_profile=profile,
    )


async def open_candidate_for(
    service: ExperimentToolService, request: PlannerRequest
) -> int:
    """由服务端把 job 的目标实验装进工作态，返回打开时的 `state_version`。

    不是让模型去猜该怎么打开：作用域在 JobContext 里钉死，之后它只能碰这个实验。
    """
    await service.open_experiment(
        OpenExperimentInput(
            experiment_id=str(request.experiment_id),
            template_id=request.template_id,
            revision_id=str(request.base_revision),
        )
    )
    state = await service.candidates.load()
    return state.state_version if state is not None else 0


@dataclass
class DeepAgentRunner:
    """生产端口：模型自主调用受控工具，成果直接落在持久候选上。"""

    conn: asyncpg.Connection
    engine: EngineClient
    artifact_dir: Path
    max_turns: int = 30
    model_factory: Callable[..., Any] = create_model
    profile: str = "deepagents"

    async def make_service(self, request: PlannerRequest) -> ExperimentToolService:
        row = await self.conn.fetchrow(
            "select owner_id, lease_token from jobs where id = $1", request.job_id
        )
        if row is None:
            raise Rejected("JOB_NOT_FOUND", str(request.job_id))
        job = JobContext(
            job_id=request.job_id,
            owner_id=row["owner_id"],
            lease_token=row["lease_token"] or "",
            experiment_id=request.experiment_id,
            base_revision=request.base_revision,
        )
        return ExperimentToolService(
            engine_client=self.engine, conn=self.conn,
            artifact_dir=self.artifact_dir, job=job,
        )

    async def run(self, request: PlannerRequest) -> AgentRunRecord:
        service = await self.make_service(request)
        baseline_version = await open_candidate_for(service, request)

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
        return await finish_run(
            self.conn,
            service=service,
            baseline_version=baseline_version,
            profile=self.profile,
            tool_calls_total=out["tool_calls_total"],
            trace={
                "profile": self.profile,
                "tool_calls_total": out["tool_calls_total"],
                "distinct_tools": out["distinct_tools"],
                "validation_rounds": out["validation_rounds"],
                "trace": out["trace"],
            },
        )
