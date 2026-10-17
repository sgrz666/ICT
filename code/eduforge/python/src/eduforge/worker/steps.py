"""生产组合根：把五个阶段接到真实协作者上（§2.2 调用栈）。

之前那条链只在测试里就地拼过，只能证明"零件能拼"。Demo 必须走这条，
否则测的是一条链、跑的是另一条。

**执行语义在 Gate A 收敛成一条**：Agent（或对照基线的固定提案）通过受控工具
改动的是数据库里的候选行；Worker 之后的 editing/building/validating/packaging
全部消费这同一行候选。以前这里会在基线上重放一遍 `EditProposal` 的操作、
再把重放结果当成交付物——那份场景从没被模型验过，「验证什么就发布什么」
当场失效。`operations_from_trace` 从此只作审计与对照，不在生产路径上决定交付。

规划端口仍可注入两种实现：有 `run()` 的是候选 Runner（生产用），
只有 `plan()` 的旧规划器由 `ProposalRunner` 适配到同一条候选写入路径上。
每个阶段都只从数据库与磁盘取事实（内存 cache 只是同一次运行内的加速）：
阶段是 at-least-once 的，接管者可能从 packaging 才开始跑，那时 planning 的返回值
早就不在了。这与 coordinator 里"唯一可信的是已落下的事件"是同一条要求。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from eduforge.application.candidate_service import CandidateService, CandidateState
from eduforge.domain.contracts import EditProposal, PlannerRequest, SetParameter, SetView
from eduforge.domain.errors import ConflictError, DeliveryIntegrityError
from eduforge.experiment_tools.contracts import (
    BuildPackageInput,
    InspectSceneInput,
    JobContext,
    RunValidationInput,
)
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.candidate_repository import CandidateVersionConflict
from eduforge.infrastructure.db.repositories import (
    JobRepository,
    artifact_id_for,
    derived_id,
    revision_id_for,
)
from eduforge.application.package_builder import PackageBuilder, verify_package_on_disk
from eduforge.application.publication import Publisher
from eduforge.worker.errors import TerminalError


class PlannerPort(Protocol):
    async def plan(self, request: PlannerRequest) -> EditProposal:
        ...


@dataclass
class StaticPlanner:
    """注入固定提案，只用于无 key 下驱动链路。"""

    proposal: EditProposal

    async def plan(self, request: PlannerRequest) -> EditProposal:
        return self.proposal


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
    planner: Any
    lease_token: str = ""
    cache: dict[str, Any] = field(default_factory=dict)
    guard: Any | None = None

    def _check_execution(self) -> None:
        """每个阶段开头都问一次执行权（心跳的判定结果在这里生效）。

        丢了租约还继续写，就是两个 Worker 往同一个实验上盖版本——数据库最后
        那道 `lease_token` 守卫只在发布事务里，改场景与落盘都发生在它之前。
        """
        if self.guard is not None:
            self.guard.check_active()

    async def _check_execution_now(self) -> None:
        """发布前当场问库，不吃后台心跳的旧结论。"""
        if self.guard is not None:
            await self.guard.check_now()

    async def _base(self, job_id: UUID) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """select j.id as job_id, j.owner_id, j.experiment_id, j.base_revision, j.prompt,
                      j.work_order, e.template_id, r.native_data::text as native
               from jobs j
               join experiments e on e.id = j.experiment_id
               join experiment_revisions r on r.id = j.base_revision
               where j.id = $1""",
            job_id,
        )
        if row is None:
            raise TerminalError("JOB_NOT_FOUND", str(job_id))
        out = dict(row)
        # 留下原始文本指纹：后面要断言基线版本在编辑之后仍是同一份字节
        out["native_digest"] = hashlib.sha256(out["native"].encode("utf-8")).hexdigest()
        out["native"] = json.loads(out["native"])
        return out

    async def _base_untouched(self, base: dict[str, Any]) -> bool:
        """基线版本必须逐字节仍是取回来的那一份——这才叫可回滚。

        这里原来写成 `(base["native"] != result["native"]) or True`：恒真，
        `validation/policies.py` 的 base_untouched 判据因此永远不会失败，
        README 宣称的那道闸门实际不存在。
        """
        now_text = await self.conn.fetchval(
            "select native_data::text from experiment_revisions where id = $1", base["base_revision"]
        )
        if now_text is None:
            return False
        return hashlib.sha256(now_text.encode("utf-8")).hexdigest() == base["native_digest"]

    def _job(self, base: dict[str, Any]) -> JobContext:
        return JobContext(
            job_id=base["job_id"],
            owner_id=base["owner_id"],
            lease_token=self.lease_token,
            experiment_id=base["experiment_id"],
            base_revision=base["base_revision"],
        )

    def _service(self, base: dict[str, Any]) -> ExperimentToolService:
        """Worker 用的工具服务：与 Agent 同一套实现、同一个候选行。

        每个阶段新建一个实例是有意的——它必须能从库里把候选读回来，
        否则接管者一重启就只剩内存里那份不存在的工作态。
        执行权检查一并传进去：丢权之后的写动作连引擎都不该碰。
        """
        return ExperimentToolService(
            engine_client=self.engine, conn=self.conn,
            artifact_dir=self.artifact_dir, job=self._job(base),
            execution_check=self.guard.check_active if self.guard is not None else None,
        )

    async def _candidate(self, base: dict[str, Any]) -> CandidateState:
        state = await CandidateService(self.conn, job=self._job(base)).load()
        if state is None:
            raise TerminalError("CANDIDATE_MISSING", str(base["job_id"]))
        return state

    @staticmethod
    def _terminal(exc: Exception, stage: str) -> TerminalError:
        """工具层的拒绝要变成**可见的终态**，不能像崩溃那样等租约过期。"""
        if isinstance(exc, ConflictError):
            text = str(exc)
            if "科学验证" in text:
                return TerminalError("VALIDATION_NOT_PASSED", text)
            if "执行权" in text or "LEASE_LOST" in text:
                return TerminalError("LEASE_LOST", text)
            if "已被取消" in text:
                return TerminalError("JOB_CANCELLED", text)
            if "候选" in text:
                return TerminalError("CANDIDATE_CONFLICT", text)
            return TerminalError("TOOL_CONFLICT", text)
        if isinstance(exc, CandidateVersionConflict):
            return TerminalError("CANDIDATE_VERSION_CONFLICT", str(exc))
        code = getattr(exc, "code", None) or getattr(exc, "reason", None) or "TOOL_ERROR"
        return TerminalError(str(code), str(exc))

    async def planning(self, job_id: UUID) -> dict[str, Any]:
        self._check_execution()
        # 把执行权守护交给端口：模型在循环里每一次写候选都要先过这道闸
        # （丢租约之后还能继续改场景，是 Gate B §B.1 点名的行为）。
        for attr, value in (("guard", self.guard), ("lease_token", self.lease_token)):
            if value is not None and hasattr(self.planner, attr) and getattr(self.planner, attr) is None:
                setattr(self.planner, attr, value)
        base = await self._base(job_id)
        if not base["prompt"]:
            raise TerminalError("PROMPT_MISSING", str(job_id))
        request = PlannerRequest(
            job_id=job_id,
            experiment_id=base["experiment_id"],
            base_revision=base["base_revision"],
            template_id=base["template_id"],
            prompt=base["prompt"],
        )
        runner = self.planner
        if not hasattr(runner, "run"):
            from eduforge.agent.proposal_runner import ProposalRunner

            runner = ProposalRunner(
                conn=self.conn, engine=self.engine,
                artifact_dir=self.artifact_dir, planner=runner,
                guard=self.guard, lease_token=self.lease_token,
            )
        try:
            record = await runner.run(request)
        except TerminalError:
            raise
        except Exception as exc:
            raise self._terminal(exc, "planning") from exc
        return record.model_dump(mode="json")

    async def editing(self, job_id: UUID) -> dict[str, Any]:
        """编辑阶段不再重新应用操作：它核对待交付候选是否被引擎接受，
        并证明基线版本仍是同一份字节。

        纯视图任务以前在这一步被判死：没有参数修改时这里会构造一个不带
        `base_untouched` 的伪结果，`bool(result.get("base_untouched"))` 恒为 False。
        现在引擎观察的就是候选本身，字段由引擎给（`main.ts` 比对入参与产出）。
        """
        self._check_execution()
        base = await self._base(job_id)
        state = await self._candidate(base)
        eng = await self.engine.apply(state.native_data, [])
        if not eng.get("validation", {}).get("ok"):
            raise TerminalError("UPSTREAM_REJECTED", str(eng.get("validation")))
        untouched = bool(eng.get("base_untouched")) and await self._base_untouched(base)
        self.cache["engine_result"] = eng
        return {
            "base_untouched": untouched,
            "version": state.native_data.get("version"),
            "processed_ray_count": eng.get("measurement", {}).get("processedRayCount", 0),
            "state_version": state.state_version,
            "content_hash": state.content_hash,
        }

    async def building(self, job_id: UUID) -> dict[str, Any]:
        """构建走工具服务那一条实现：冻结候选、落盘、算指纹，不再各写一份。"""
        self._check_execution()
        base = await self._base(job_id)
        service = self._service(base)
        try:
            out = await service.build_package(BuildPackageInput(
                experiment_id=str(base["experiment_id"]), export_offline_zip=False
            ))
        except TerminalError:
            raise
        except Exception as exc:
            raise self._terminal(exc, "building") from exc
        cand = UUID(out.candidate_revision_id)
        await self.conn.execute(
            "update jobs set candidate_revision_id = $2 where id = $1", job_id, cand
        )
        native_artifact = next(
            (a for a in out.artifacts if a["storage_key"].replace("\\", "/").endswith("native.json")),
            None,
        )
        if native_artifact is None:
            raise TerminalError("BUILD_ARTIFACT_MISSING", str(cand))
        target = artifact_path(self.artifact_dir, cand)
        return {
            "candidate_revision_id": out.candidate_revision_id,
            "storage_key": native_artifact["storage_key"],
            "bytes": target.stat().st_size,
            "sha256": out.sha256,
        }

    async def validating(self, job_id: UUID) -> dict[str, Any]:
        """验证用工具服务同一条实现，对**冻结后的候选**重跑一次真实引擎观测。"""
        self._check_execution()
        base = await self._base(job_id)
        service = self._service(base)
        try:
            val = await service.run_validation(
                RunValidationInput(experiment_id=str(base["experiment_id"])), final=True
            )
        except TerminalError:
            raise
        except Exception as exc:
            raise self._terminal(exc, "validating") from exc
        insp = await service.inspect_scene(InspectSceneInput(experiment_id=str(base["experiment_id"])))
        # unverifiable_checks 是「测不出来」而不是「测出来不成立」：
        # 两者都拦得住发布，但混在 failed 里就让人以为物理不成立。
        return {
            "verdict": val.verdict,
            "failed_checks": [c["id"] for c in val.checks if c.get("status") == "fail"],
            "unverifiable_checks": [c["id"] for c in val.checks if c.get("status") == "na"],
            "focal_length_cm": insp.parameters.get("focal_length_cm"),
            "object_distance_cm": insp.parameters.get("object_distance_cm"),
        }

    async def packaging(self, job_id: UUID) -> dict[str, Any]:
        """发布事务。verdict、候选字节、产物登记全部取自持久化的事实。"""
        # 发布是最后一道写动作：当场向库确认执行权还在自己手上，不吃心跳的旧结论
        await self._check_execution_now()
        base = await self._base(job_id)
        state = await self._candidate(base)
        cand = revision_id_for(job_id, state.content_hash)

        if not state.is_validated or state.validation_id is None:
            raise TerminalError("REPORT_MISSING", f"候选 {cand} 没有绑定在当前内容上的验证报告")
        row = await self.conn.fetchrow(
            "select verdict from validation_reports where id = $1", state.validation_id
        )
        if row is None:
            raise TerminalError("REPORT_MISSING", str(state.validation_id))
        if row["verdict"] != "passed":
            raise TerminalError("VALIDATION_NOT_PASSED", row["verdict"])

        # 交付字节由统一构建器产出并逐字节回读核对（含离线运行包）：
        # Worker 与工具层不再是两份写盘代码，publish 登记的 artifacts 就是这一份。
        try:
            built = await PackageBuilder(engine_client=self.engine, artifact_dir=self.artifact_dir).build(
                state, include_offline=True
            )
        except DeliveryIntegrityError as exc:
            # 交付完整性失败要让任务可见地终态，不能像崩溃那样等租约过期再重试一遍。
            # code 用异常自己带的那个（DELIVERY_INTEGRITY / OFFLINE_NOT_RENDERED），
            # 统一压成一个字符串会让"包打不开"和"清单核对不上"在报表里长得一样。
            raise TerminalError(exc.code or "DELIVERY_INTEGRITY", str(exc)) from exc
        digest = built.native_sha256
        artifacts = built.artifacts

        # 发布前最后一道磁盘核对（§C.5b）：清单说的字节必须就是盘上的字节。
        # building 与 packaging 之间可能崩过、也可能被接管者在另一时刻重跑，
        # 只信"我刚刚写过"是不够的。
        disk_check: dict[str, Any] | None = None
        if built.offline:
            disk_check = await asyncio.to_thread(verify_package_on_disk, Path(built.offline["dir"]))
            if not disk_check["ok"]:
                raise TerminalError(
                    "PACKAGE_DRIFT",
                    f"离线包磁盘与清单不符：{disk_check['reason']}，"
                    f"changed={disk_check['changed']} missing={disk_check['missing']} "
                    f"unexpected={disk_check['unexpected']}",
                )

        await Publisher(self.conn).publish(
            job_id=job_id,
            lease_token=self.lease_token,
            experiment_id=base["experiment_id"],
            base_revision=state.base_revision,
            candidate_revision_id=cand,
            native_data=state.native_data,
            report_verdict=row["verdict"],
            artifacts=artifacts,
            lesson={"views": state.teaching_views},
            # 幂等重放时事务会核对：已登记的字节必须是这一份，否则不是重放而是抢同一个 id
            expected_native_sha256=digest,
        )
        await CandidateService(self.conn, job=self._job(base)).set_status("published")
        return {
            "head_revision_id": str(cand),
            "artifact_id": artifacts[0]["id"],
            "sha256": digest,
            "content_hash": state.content_hash,
            # 交付了什么要能在任务记录里看到：离线包文件数、整包摘要与发布前的磁盘核对结论
            "offline_package": built.offline,
            "package_disk_check": disk_check,
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
    conn: asyncpg.Connection, *, engine_url: str, artifact_dir: Path, planner: Any,
    lease_seconds: int = 90, pool: asyncpg.Pool | None = None, heartbeat_seconds: float = 25.0,
    max_attempts: int = 5,
):
    """组合根：Worker 拿到租约之后才构造步骤，packaging 要靠 lease_token 证明执行权。

    给了 `pool` 才会起心跳守护器（心跳必须用池里的另一条连接，不能与 Agent SQL 抢
    同一条）。不给就是旧行为：租约到点即失效，长任务会丢执行权——那条路径只该出现在
    单元测试里，生产入口必须传池。
    """
    from eduforge.application.coordinator import Coordinator
    from eduforge.worker.main import Worker

    repo = JobRepository(conn)

    def factory(lease_token: str, guard: Any | None = None) -> dict[str, Any]:
        chain = Chain(
            conn=conn, engine=EngineClient(engine_url), artifact_dir=Path(artifact_dir),
            planner=planner, lease_token=lease_token, guard=guard,
        )
        return chain.steps()

    return Worker(
        repo=repo,
        coordinator=Coordinator(repo=repo, steps={}),
        lease_seconds=lease_seconds,
        steps_factory=factory,
        lease_pool=pool,
        heartbeat_seconds=heartbeat_seconds,
        max_attempts=max_attempts,
    )
