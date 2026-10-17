"""把一份 `EditProposal` 落到候选上：固定提案与旧 graph 的对照基线。

它与 `DeepAgentRunner` 交回同一种记录，差别只在决策来源——代码给的清单 vs 模型
自主的工具调用。保留这条路径是为了**能对照**（Benchmark 的 `agent_graph` 基线、
无 key 时的链路验证），而不是给流水线留一个「不用模型也能变绿」的出口。

关键点：清单也是通过同一套受控工具写进候选的，Worker 不再另有一套 `_apply` 重放。
两条路径共用同一个候选写入语义，才不会「测的是一条链、跑的又是另一条」。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import asyncpg

from eduforge.agent.deepagents_runner import finish_run, open_candidate_for
from eduforge.agent.policy import Rejected, authorize, load_template
from eduforge.application.candidate_service import AgentRunRecord
from eduforge.domain.contracts import PlannerRequest, SetParameter, SetView
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    ConfigureTeachingViewsInput,
    JobContext,
)
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient


class ProposalPort(Protocol):
    async def plan(self, request: PlannerRequest):
        ...


@dataclass
class ProposalRunner:
    """`PlannerPort` → 候选：旧规划器不改接口，也能接到统一执行链上。"""

    conn: asyncpg.Connection
    engine: EngineClient
    artifact_dir: Path
    planner: ProposalPort
    profile: str = "proposal_baseline"
    guard: Any | None = None
    # Worker 领取到的 token；回读 jobs 会把新主人的凭据误认成自己的（见 deepagents_runner 同处注释）
    lease_token: str | None = None

    async def run(self, request: PlannerRequest) -> AgentRunRecord:
        proposal = await self.planner.plan(request)

        # §4.3 授权链在服务端构造 WorkOrder：模型不能自己决定归属或基础版本。
        # 清单先过闸门再落候选，和旧 Chain.planning 是同一道 authorize。
        template = load_template(request.template_id)
        order = authorize(request, template, proposal)
        if order.proposal.route == "code":
            raise Rejected("CODE_ROUTE_NOT_EXECUTED", "引擎侧未实现代码路径")
        await self.conn.execute(
            "update jobs set work_order = $2::jsonb where id = $1",
            request.job_id, order.model_dump_json(),
        )

        owner = await self.conn.fetchval("select owner_id from jobs where id = $1", request.job_id)
        token = self.lease_token
        if token is None:
            token = await self.conn.fetchval("select lease_token from jobs where id = $1", request.job_id) or ""
        service = ExperimentToolService(
            engine_client=self.engine, conn=self.conn, artifact_dir=self.artifact_dir,
            job=JobContext(
                job_id=request.job_id, owner_id=owner, lease_token=token,
                experiment_id=request.experiment_id, base_revision=request.base_revision,
            ),
            execution_check=self.guard.check_active if self.guard is not None else None,
        )
        baseline_version = await open_candidate_for(service, request)

        applied = 0
        for op in order.proposal.operations:
            if isinstance(op, SetParameter):
                await service.apply_scene_patch(ApplyScenePatchInput(
                    experiment_id=str(request.experiment_id), edits=[op.model_dump()]
                ))
                applied += 1
            elif isinstance(op, SetView):
                await service.configure_teaching_views(ConfigureTeachingViewsInput(
                    experiment_id=str(request.experiment_id),
                    views={op.view_id: {"visible": op.visible}},
                ))
                applied += 1

        return await finish_run(
            self.conn,
            service=service,
            baseline_version=baseline_version,
            profile=self.profile,
            tool_calls_total=applied,
            trace={
                "profile": self.profile,
                "operations": [op.model_dump() for op in order.proposal.operations],
                "applied": applied,
            },
        )
