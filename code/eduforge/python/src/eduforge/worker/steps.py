"""生产组合根：把五个阶段接到真实协作者上（§2.2 调用栈）。

之前那条链只在测试里就地拼过，只能证明"零件能拼"。Demo 必须走这条，
否则测的是一条链、跑的是另一条。

规划端口 PlannerPort 是**注入**的：真实实现是 LangGraph + DeepSeek（要 key），
无 key 时由测试与本地演示注入固定 EditProposal。这不构成规划能力的证据，
GATE-6 的模型对照仍然开放。

每个阶段都只从数据库与磁盘取事实（内存 cache 只是同一次运行内的加速）：
阶段是 at-least-once 的，接管者可能从 packaging 才开始跑，那时 planning 的返回值
早就不在了。这与 coordinator 里"唯一可信的是已落下的事件"是同一条要求。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from eduforge.agent.policy import authorize, load_template
from eduforge.application.publication import Publisher
from eduforge.domain.contracts import EditProposal, PlannerRequest, SetParameter, SetView, WorkOrder
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.repositories import JobRepository
from eduforge.validation.policies import build_report
from eduforge.worker.errors import TerminalError

# 候选版本与产物 id 由 job_id 派生，不用随机 uuid：
# 崩在 packaging 里重来时必须落在同一批 id 上，否则重跑会插出第二个候选版本、
# 或把同一份字节登记成两个产物。
ID_NAMESPACE = UUID("6b1c9df8-7f6a-4f0e-9b9f-4b8a9c1edf01")


def derived_id(job_id: UUID, kind: str) -> UUID:
    return uuid.uuid5(ID_NAMESPACE, f"{job_id}:{kind}")


class PlannerPort(Protocol):
    async def plan(self, request: PlannerRequest) -> EditProposal:
        ...


@dataclass
class StaticPlanner:
    """注入固定提案，只用于无 key 下驱动链路。"""

    proposal: EditProposal

    async def plan(self, request: PlannerRequest) -> EditProposal:
        return self.proposal


def scene_bytes(native: dict[str, Any]) -> bytes:
    """交付字节的唯一写法。哈希锁这份字节，下载也交这份字节。"""
    return (json.dumps(native, ensure_ascii=False) + "\n").encode("utf-8")


def artifact_path(artifact_dir: Path, candidate_revision: UUID) -> Path:
    return artifact_dir / "revisions" / str(candidate_revision) / "native.json"


def object_distance_cm(native: dict[str, Any], units_per_unit: int) -> float:
    """物距从要交付的那份场景里读，不抄第二份常量。

    验证要用独立参考式 v=f·u/(u−f)，u 错了整条对照就失去意义；
    把 30.0 写死在代码里会在有人挪动物点时静默失真。
    """
    sources = [o for o in native.get("objs", []) if o.get("type") == "PointSource"]
    lenses = [o for o in native.get("objs", []) if o.get("type") == "IdealLens"]
    if len(sources) != 1 or len(lenses) != 1:
        raise TerminalError(
            "SCENE_SHAPE_UNSUPPORTED", f"PointSource={len(sources)} IdealLens={len(lenses)}"
        )
    lens = lenses[0]
    lens_x = (float(lens["p1"]["x"]) + float(lens["p2"]["x"])) / 2
    return abs(float(sources[0]["x"]) - lens_x) / units_per_unit


@dataclass
class Chain:
    """一次 Worker 运行里五个阶段的共同依赖。"""

    conn: asyncpg.Connection
    engine: EngineClient
    artifact_dir: Path
    planner: PlannerPort
    lease_token: str = ""
    cache: dict[str, Any] = field(default_factory=dict)

    async def _base(self, job_id: UUID) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """select j.id as job_id, j.experiment_id, j.base_revision, j.prompt, j.work_order,
                      e.template_id, r.native_data::text as native
               from jobs j
               join experiments e on e.id = j.experiment_id
               join experiment_revisions r on r.id = j.base_revision
               where j.id = $1""",
            job_id,
        )
        if row is None:
            raise TerminalError("JOB_NOT_FOUND", str(job_id))
        out = dict(row)
        out["native"] = json.loads(out["native"])
        return out

    async def _order(self, job_id: UUID) -> tuple[dict[str, Any], WorkOrder, SetParameter | None, list[SetView]]:
        """授权结果读自 jobs.work_order：planning 之后的一切都必须能只靠持久化事实重建。"""
        base = await self._base(job_id)
        if not base["work_order"]:
            raise TerminalError("WORK_ORDER_MISSING", str(job_id))
        order = WorkOrder.model_validate_json(base["work_order"])
        ops = order.proposal.operations
        if not ops:
            raise TerminalError("NO_OPERATIONS", str(job_id))
        param_edits = [op for op in ops if isinstance(op, SetParameter)]
        view_edits = [op for op in ops if isinstance(op, SetView)]
        param_edit = param_edits[0] if param_edits else None
        return base, order, param_edit, view_edits

    async def planning(self, job_id: UUID) -> dict[str, Any]:
        base = await self._base(job_id)
        if not base["prompt"]:
            raise TerminalError("PROMPT_MISSING", str(job_id))
        template = load_template(base["template_id"])
        request = PlannerRequest(
            job_id=job_id,
            experiment_id=base["experiment_id"],
            base_revision=base["base_revision"],
            template_id=base["template_id"],
            prompt=base["prompt"],
        )
        proposal = await self.planner.plan(request)
        # §4.3 授权链在服务端构造 WorkOrder：模型不能自己决定归属或基础版本
        order = authorize(request, template, proposal)
        if order.proposal.route == "code":
            # Engine Host 没有可执行的 code 路径。宁可明确失败，
            # 也不拿 config 路径的结果冒充"代码改动成功"。
            raise TerminalError("CODE_ROUTE_NOT_EXECUTED", "引擎侧未实现代码路径")
        if not order.proposal.operations:
            raise TerminalError("NO_OPERATIONS", "没有可执行操作")
        await self.conn.execute(
            "update jobs set work_order = $2::jsonb where id = $1",
            job_id, order.model_dump_json(),
        )
        param_edits = [op for op in order.proposal.operations if isinstance(op, SetParameter)]
        edit = param_edits[0] if param_edits else None
        u_cm = object_distance_cm(base["native"], template.units_per_unit)
        return {
            "route": order.proposal.route,
            "operation_count": len(order.proposal.operations),
            "entity_id": edit.entity_id if edit else None,
            "parameter": edit.parameter if edit else None,
            "value": edit.value if edit else None,
            "template_id": base["template_id"],
            "object_distance_cm": u_cm,
        }

    async def _apply(self, job_id: UUID) -> dict[str, Any]:
        if "engine_result" in self.cache:
            return self.cache["engine_result"]
        base, _order, edit, _views = await self._order(job_id)
        if edit is not None:
            result = await self.engine.apply(base["native"], edit.model_dump())
        else:
            result = {
                "base_untouched": True,
                "native": base["native"],
                "validation": {"ok": True, "error": None, "objs": base["native"].get("objs", [])},
                "measurement": {"probes": [], "processedRayCount": 0},
            }
        if not result.get("validation", {}).get("ok"):
            raise TerminalError("UPSTREAM_REJECTED", str(result.get("validation")))
        self.cache["engine_result"] = result
        return result

    async def editing(self, job_id: UUID) -> dict[str, Any]:
        result = await self._apply(job_id)
        return {
            "base_untouched": bool(result.get("base_untouched")),
            "version": result["native"].get("version"),
            "processed_ray_count": result["measurement"].get("processedRayCount"),
        }

    async def building(self, job_id: UUID) -> dict[str, Any]:
        """把候选版本落成文件，并算出要交付的那份字节的指纹。"""
        result = await self._apply(job_id)
        cand = derived_id(job_id, "revision")
        payload = scene_bytes(result["native"])
        target = artifact_path(self.artifact_dir, cand)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        # 候选 id 由 job_id 派生：重跑写同一个值，不会互相覆盖成不同版本
        await self.conn.execute(
            "update jobs set candidate_revision_id = $2 where id = $1", job_id, cand
        )
        return {
            "candidate_revision_id": str(cand),
            "storage_key": str(target.relative_to(self.artifact_dir)),
            "bytes": len(payload),
            "sha256": digest,
        }

    async def validating(self, job_id: UUID) -> dict[str, Any]:
        base, _order, edit, views = await self._order(job_id)
        template = load_template(base["template_id"])
        result = await self._apply(job_id)
        report = build_report(
            job_id=str(job_id),
            edit=edit,
            view_edits=views,
            engine_result=result,
            object_distance_cm=object_distance_cm(base["native"], template.units_per_unit),
            units_per_unit=template.units_per_unit,
            allowed_views=template.views,
        )
        await Publisher(self.conn).record_report(job_id=job_id, report=report)
        return {
            "verdict": report.verdict,
            "failed_checks": [c.id for c in report.checks if not c.passed],
        }

    async def packaging(self, job_id: UUID) -> dict[str, Any]:
        """发布事务。verdict 与候选字节都取自持久化的事实。"""
        row = await self.conn.fetchrow(
            """select verdict from validation_reports
               where job_id = $1 order by created_at desc limit 1""",
            job_id,
        )
        if row is None:
            raise TerminalError("REPORT_MISSING", str(job_id))
        if row["verdict"] != "passed":
            raise TerminalError("VALIDATION_NOT_PASSED", row["verdict"])

        base, _order, _edit, _views = await self._order(job_id)
        cand = derived_id(job_id, "revision")
        target = artifact_path(self.artifact_dir, cand)
        try:
            payload = target.read_bytes()
        except FileNotFoundError:
            raise TerminalError("ARTIFACT_FILE_MISSING", str(target)) from None
        digest = hashlib.sha256(payload).hexdigest()

        await Publisher(self.conn).publish(
            job_id=job_id,
            lease_token=self.lease_token,
            experiment_id=base["experiment_id"],
            base_revision=base["base_revision"],
            candidate_revision_id=cand,
            native_data=json.loads(payload),
            report_verdict=row["verdict"],
            artifacts=[{
                "id": str(derived_id(job_id, "artifact")),
                "storage_key": str(target.relative_to(self.artifact_dir)),
                "sha256": digest,
                "media_type": "application/json",
            }],
        )
        return {
            "head_revision_id": str(cand),
            "artifact_id": str(derived_id(job_id, "artifact")),
            "sha256": digest,
        }

    def steps(self) -> dict[str, Any]:
        return {
            "planning": self.planning,
            "editing": self.editing,
            "building": self.building,
            "validating": self.validating,
            "packaging": self.packaging,
        }


def make_worker(
    conn: asyncpg.Connection, *, engine_url: str, artifact_dir: Path, planner: PlannerPort,
    lease_seconds: int = 90,
):
    """组合根：Worker 拿到租约之后才构造步骤，packaging 要靠 lease_token 证明执行权。"""
    from eduforge.application.coordinator import Coordinator
    from eduforge.worker.main import Worker

    repo = JobRepository(conn)

    def factory(lease_token: str) -> dict[str, Any]:
        chain = Chain(
            conn=conn, engine=EngineClient(engine_url), artifact_dir=Path(artifact_dir),
            planner=planner, lease_token=lease_token,
        )
        return chain.steps()

    return Worker(
        repo=repo,
        coordinator=Coordinator(repo=repo, steps={}),
        lease_seconds=lease_seconds,
        steps_factory=factory,
    )
