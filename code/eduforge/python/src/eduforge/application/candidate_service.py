"""候选工作态的业务层：内容指纹、版本推进、验证绑定、冻结。

这里定的规则是全链路唯一的一份：Agent 改的是这行候选，Worker 验证、构建、
发布的也是这行候选。**Trace 只作审计**，不再被折算成操作清单重放第二遍。

内容哈希 `content_hash` 覆盖原生场景与教学视图两部分，采用 canonical JSON：
- 键按字典序排序，`ensure_ascii=False`，分隔符固定为 `,`/`:`；
- 浮点走 12 位有效数字，整数值浮点归一成整数——Postgres `jsonb` 会把 `150`
  读回成 int、把 `15.0` 读回成 float，不归一就会给同一份场景算出两个哈希；
- `NaN`/`Infinity` 直接拒：它们进不了可交付场景，却能让哈希漂移。

写路径一律带 `state_version` 做 CAS：对不上就抛冲突，不静默覆盖。
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

import asyncpg
from pydantic import Field

from eduforge.domain.contracts import Contract
from eduforge.infrastructure.db.candidate_repository import (
    CandidateFrozen,
    CandidateRepository,
    CandidateVersionConflict,
)
from eduforge.infrastructure.db.repositories import (
    ID_NAMESPACE,
    artifact_id_for,
    candidate_id_for,
    revision_id_for,
)


class JobScope(Protocol):
    """服务端签发的执行上下文里，候选需要的那两个字段。

    这里不 import `experiment_tools.contracts.JobContext`：那个包的 `__init__`
    会导入工具服务，而工具服务要用本模块——应用层反过来依赖工具层会把环闭上。
    """

    @property
    def job_id(self) -> UUID: ...

    @property
    def owner_id(self) -> str: ...


class AgentRunRecord(Contract):
    """一次 Agent 执行结束后，后端拿到的**候选完成记录**。

    刻意不含 `published`，也不含操作清单：模型说做了什么不算数，库里那行候选
    是什么才算数。发布与否由 Worker/Publisher 依据验证报告与执行权另行决定。
    """

    candidate_id: UUID
    content_hash: str
    state_version: int
    validation_id: UUID | None = None
    validation_verdict: str | None = None
    agent_trace_ref: str
    terminal_state: Literal[
        "candidate_ready",  # 有写入且报告 passed，可进构建/发布
        "candidate_unvalidated",  # 有写入但没验过
        "validation_failed",  # 验过但没过
        "rejected_no_operations",  # 一次有效写入都没有
    ]
    tool_calls_total: int = 0
    model_profile: str = "unknown"


class CandidateState(Contract):
    """一行未发布候选。`job_id` 唯一，进程重启后仍能从库里读回同一份。"""

    candidate_id: UUID
    job_id: UUID
    experiment_id: UUID
    base_revision: UUID
    owner_id: str
    template_id: str
    native_data: dict[str, Any] = Field(default_factory=dict)
    teaching_views: dict[str, Any] = Field(default_factory=dict)
    edits: list[dict[str, Any]] = Field(default_factory=list)
    content_hash: str
    state_version: int = 0
    status: str = "editing"
    validation_id: UUID | None = None
    validation_hash: str | None = None
    updated_at: datetime | None = None

    @property
    def is_frozen(self) -> bool:
        return self.status in ("frozen", "published")

    @property
    def is_validated(self) -> bool:
        """只承认钉在当前内容上的验证结论；内容变了就是没验过。"""
        return (
            self.validation_id is not None
            and self.validation_hash == self.content_hash
        )


def _canonical(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("候选内容里出现 NaN/Infinity，无法计算稳定哈希")
        if value.is_integer():
            return int(value)
        # 12 位有效数字：比 double 的十进制往返短，足以区分真实物理量，
        # 又不会因为上游末位抖动而把同一份场景算成两个候选。
        return float(f"{value:.12g}")
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def canonical_json(native: dict[str, Any], views: dict[str, Any]) -> str:
    payload = _canonical({"native": native, "views": views or {}})
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_fingerprint(native: dict[str, Any], views: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(native, views).encode("utf-8")).hexdigest()


def native_bytes(native: dict[str, Any]) -> bytes:
    """交付字节的唯一写法：哈希锁这份字节，下载也交这份字节。

    工具路径与 Worker 路径以前各写一种（一种带缩进、一种紧凑），同一份场景
    会产生两个 sha256，"验证过的哈希等于发布出去的哈希"根本无从核对。
    """
    return (json.dumps(native, ensure_ascii=False) + "\n").encode("utf-8")


def views_bytes(views: dict[str, Any]) -> bytes:
    return (json.dumps(views, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class CandidateService:
    """候选的读写门面。有库就落库，没库就显式退化为进程内缓存并如实标注。"""

    def __init__(self, conn: asyncpg.Connection | None, *, job: JobScope | None = None) -> None:
        self.job = job
        self.repo = CandidateRepository(conn) if conn is not None else None
        self._mem: dict[UUID, CandidateState] = {}
        self._memory_key: UUID | None = None

    @property
    def persistent(self) -> bool:
        return self.repo is not None and self.job is not None

    def note_experiment(self, experiment_id: UUID | str) -> UUID:
        """没有 job 时（单测与纯链路演练）给缓存一个稳定键。

        这条路径**从不落库**：没有 JobContext 就没有归属答案，
        把候选写成一行没有主人的记录比写不进更糟。
        """
        self._memory_key = uuid.uuid5(ID_NAMESPACE, f"memory:{experiment_id}")
        return self._memory_key

    def key(self) -> UUID:
        if self.job is not None:
            return self.job.job_id
        if self._memory_key is not None:
            return self._memory_key
        raise CandidateFrozen("没有服务端签发的 JobContext，无法确定候选归属")

    def revision_id(self, state: CandidateState) -> UUID:
        return revision_id_for(state.job_id, state.content_hash)

    def artifact_id(self, state: CandidateState, name: str, digest: str) -> UUID:
        return artifact_id_for(state.job_id, name, digest)

    async def open(
        self,
        *,
        experiment_id: UUID,
        base_revision: UUID,
        owner_id: str,
        template_id: str,
        native: dict[str, Any],
        views: dict[str, Any] | None = None,
        edits: list[dict[str, Any]] | None = None,
    ) -> CandidateState:
        """取回本 job 的候选；不存在就用给定基线版本初始化一份。"""
        views = views or {}
        key = self.key()
        if not self.persistent:
            existing = self._mem.get(key)
            if existing is not None and existing.experiment_id == experiment_id:
                return existing
            state = self._state(
                key, experiment_id, base_revision, owner_id, native, views,
                template_id=template_id, edits=edits or [],
            )
            self._mem[key] = state
            return state
        row = await self.repo.initialize(
            job_id=key, experiment_id=experiment_id, base_revision=base_revision,
            owner_id=owner_id, template_id=template_id, native_data=native,
            teaching_views=views, content_hash=content_fingerprint(native, views),
            edits=edits or [],
        )
        return self._from_row(row)

    async def load(self) -> CandidateState | None:
        key = self.key()
        if not self.persistent:
            return self._mem.get(key)
        row = await self.repo.load(key)
        return self._from_row(row) if row else None

    async def write(
        self,
        *,
        native: dict[str, Any],
        views: dict[str, Any],
        expected_version: int,
        edits: list[dict[str, Any]] | None = None,
    ) -> CandidateState:
        """推进候选内容：CAS 写库，旧验证结论当场作废。

        `expected_version` 必须是调用方**读到的那一次**的 `state_version`。
        如果写成「先读最新再更新」，并发覆盖永远撞不上，CAS 就成了装饰。
        """
        key = self.key()
        current = await self.load()
        if current is None:
            raise KeyError(f"候选不存在: job {key}")
        if current.is_frozen:
            raise CandidateFrozen(
                f"候选 {current.candidate_id} 已冻结（state_version={current.state_version}），"
                "不能在冻结的版本上继续改"
            )
        next_edits = list(edits) if edits is not None else current.edits
        if current.state_version != expected_version:
            # CAS 判定放在读到的那一行上：两个进程拿着同一版候选先后写，
            # 后一个必须失败，而不是把前一份成果静默盖掉。
            raise CandidateVersionConflict(
                f"state_version 期望 {expected_version}，实际 {current.state_version}"
            )
        if not self.persistent:
            if current.state_version != expected_version:
                raise CandidateVersionConflict(
                    f"state_version 期望 {expected_version}，实际 {current.state_version}"
                )
            state = self._state(
                key, current.experiment_id, current.base_revision, current.owner_id,
                native, views,
                state_version=current.state_version + 1,
                candidate_id=current.candidate_id,
                template_id=current.template_id,
                edits=next_edits,
            )
            self._mem[key] = state
            return state
        row = await self.repo.write(
            key, native_data=native, teaching_views=views,
            content_hash=content_fingerprint(native, views),
            expected_version=expected_version, edits=next_edits,
        )
        return self._from_row(row)

    async def bind_validation(self, validation_id: UUID) -> CandidateState:
        key = self.key()
        current = await self.load()
        if current is None:
            raise KeyError(f"候选不存在: job {key}")
        if not self.persistent:
            state = current.model_copy(update={
                "validation_id": validation_id,
                "validation_hash": current.content_hash,
            })
            self._mem[key] = state
            return state
        row = await self.repo.bind_validation(key, validation_id=validation_id, content_hash=current.content_hash)
        return self._from_row(row)

    async def freeze(self) -> CandidateState:
        key = self.key()
        current = await self.load()
        if current is None:
            raise KeyError(f"候选不存在: job {key}")
        if not self.persistent:
            state = current.model_copy(update={"status": "frozen"})
            self._mem[key] = state
            return state
        row = await self.repo.freeze(key, content_hash=current.content_hash)
        return self._from_row(row)

    async def set_status(self, status: str) -> None:
        key = self.key()
        current = await self.load()
        if current is None:
            raise KeyError(f"候选不存在: job {key}")
        if not self.persistent:
            self._mem[key] = current.model_copy(update={"status": status})
            return
        await self.repo.set_status(key, status=status)

    async def rebase(self, revision_id: UUID) -> None:
        """发布成功后把候选基线推进到刚发布的那一版，供同一 job 继续编辑。"""
        key = self.key()
        if not self.persistent:
            current = self._mem.get(key)
            if current is not None:
                self._mem[key] = current.model_copy(update={
                    "base_revision": revision_id, "status": "editing"
                })
            return
        await self.repo.rebase(key, revision_id=revision_id)

    async def attach_trace(self, trace: dict[str, Any]) -> None:
        """台账只作审计：它不参与「能不能发布」的判定。"""
        key = self.key()
        if not self.persistent:
            return
        await self.repo.attach_trace(key, trace=trace)

    def _state(
        self,
        job_id: UUID,
        experiment_id: UUID,
        base_revision: UUID,
        owner_id: str,
        native: dict[str, Any],
        views: dict[str, Any],
        *,
        state_version: int = 0,
        candidate_id: UUID | None = None,
        edits: list[dict[str, Any]] | None = None,
        template_id: str = "optics.convex_lens",
    ) -> CandidateState:
        return CandidateState(
            candidate_id=candidate_id or candidate_id_for(job_id),
            job_id=job_id,
            experiment_id=experiment_id,
            base_revision=base_revision,
            owner_id=owner_id,
            template_id=template_id,
            native_data=native,
            teaching_views=views,
            edits=edits or [],
            content_hash=content_fingerprint(native, views),
            state_version=state_version,
            status="editing",
        )

    @staticmethod
    def _from_row(row: dict[str, Any]) -> CandidateState:
        return CandidateState(
            candidate_id=row["candidate_id"],
            job_id=row["job_id"],
            experiment_id=row["experiment_id"],
            base_revision=row["base_revision"],
            owner_id=row["owner_id"],
            template_id=row["template_id"],
            native_data=row["native_data"] or {},
            teaching_views=row["teaching_views"] or {},
            edits=row.get("edits") or [],
            content_hash=row["content_hash"],
            state_version=row["state_version"],
            status=row["status"],
            validation_id=row["validation_id"],
            validation_hash=row["validation_hash"],
            updated_at=row["updated_at"],
        )
