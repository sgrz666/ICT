"""未发布候选工作态的仓储层（`experiment_candidates`）。

只放 SQL 与并发守卫，业务判断（内容哈希、验证是否过期）在 `application/candidate_service.py`。

三条硬约束：
1. **一行一 job**：主键是 `job_id`，重试与接管都落在同一行，不会长出第二个候选；
2. **CAS 写入**：每次写必须带上读到的 `state_version`，对不上就拒写而不是静默覆盖；
3. **内容一变，绿灯即灭**：写路径把 `validation_id`/`validation_hash` 清空，
   旧验证结论无法再支撑构建与发布。
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from eduforge.infrastructure.db.repositories import candidate_id_for

CANDIDATE_COLUMNS = (
    "job_id, candidate_id, experiment_id, base_revision, owner_id, template_id, native_data, "
    "teaching_views, edits, content_hash, state_version, status, validation_id, "
    "validation_hash, agent_trace, created_at, updated_at"
)


class CandidateNotFound(Exception):
    """候选行不存在——调用方不能拿默认模板顶上。"""


class CandidateVersionConflict(Exception):
    """`state_version` 对不上：有人在我们读之后改过这份工作态。"""


class CandidateScopeConflict(Exception):
    """候选行已经绑到了别的实验或别的基线版本——串写，必须拒。"""


def _parse(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for col in ("native_data", "teaching_views", "agent_trace", "edits"):
        if isinstance(out.get(col), str):
            out[col] = json.loads(out[col])
    return out


class CandidateRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def load(self, job_id: UUID) -> dict[str, Any] | None:
        return _parse(await self.conn.fetchrow(
            f"select {CANDIDATE_COLUMNS} from experiment_candidates where job_id = $1", job_id
        ))

    async def initialize(
        self,
        *,
        job_id: UUID,
        experiment_id: UUID,
        base_revision: UUID,
        owner_id: str,
        template_id: str,
        native_data: dict,
        teaching_views: dict,
        content_hash: str,
        edits: list[dict] | None = None,
    ) -> dict[str, Any]:
        """首次访问创建候选行；已存在则原样返回（幂等，重试不重置工作态）。"""
        cid = candidate_id_for(job_id)
        row = await self.conn.fetchrow(
            """insert into experiment_candidates (
                   job_id, candidate_id, experiment_id, base_revision, owner_id, template_id,
                   native_data, teaching_views, edits, content_hash, state_version, status)
               values ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb,$10,0,'editing')
               on conflict (job_id) do nothing
               returning """ + CANDIDATE_COLUMNS,
            job_id, cid, experiment_id, base_revision, owner_id, template_id,
            json.dumps(native_data, ensure_ascii=False),
            json.dumps(teaching_views, ensure_ascii=False),
            json.dumps(edits or [], ensure_ascii=False),
            content_hash,
        )
        existing = _parse(row) if row is not None else await self.load(job_id)
        assert existing is not None
        if str(existing["experiment_id"]) != str(experiment_id) or str(existing["base_revision"]) != str(base_revision):
            raise CandidateScopeConflict(
                f"任务 {job_id} 的候选已绑定实验 {existing['experiment_id']}@{existing['base_revision']}，"
                f"不能改绑 {experiment_id}@{base_revision}"
            )
        return existing

    async def write(
        self,
        job_id: UUID,
        *,
        native_data: dict,
        teaching_views: dict,
        content_hash: str,
        expected_version: int,
        edits: list[dict] | None = None,
    ) -> dict[str, Any]:
        """带版本号的写入；同时作废该候选上已有的验证结论。

        `edits` 是「已通过的清单内请求」清单，验证报告要按它逐项对照最终值。
        它跟着内容一起持久化，否则进程重启后 Worker 只能重放操作或凭空验证。
        """
        row = await self.conn.fetchrow(
            """update experiment_candidates
                  set native_data = $2::jsonb, teaching_views = $3::jsonb,
                      edits = $4::jsonb, content_hash = $5,
                      state_version = state_version + 1,
                      status = 'editing', validation_id = NULL, validation_hash = NULL,
                      updated_at = now()
                where job_id = $1 and state_version = $6
                returning """ + CANDIDATE_COLUMNS,
            job_id,
            json.dumps(native_data, ensure_ascii=False),
            json.dumps(teaching_views, ensure_ascii=False),
            json.dumps(edits or [], ensure_ascii=False),
            content_hash,
            expected_version,
        )
        if row is None:
            await self._explain_failure(job_id, expected_version)
        return _parse(row)  # type: ignore[arg-type]

    async def bind_validation(
        self, job_id: UUID, *, validation_id: UUID, content_hash: str
    ) -> dict[str, Any]:
        """把验证结论钉在**当前这份内容**上；内容已变则拒绑，不产生过期绿灯。"""
        row = await self.conn.fetchrow(
            """update experiment_candidates
                  set validation_id = $2, validation_hash = $3, updated_at = now()
                where job_id = $1 and content_hash = $3
                returning """ + CANDIDATE_COLUMNS,
            job_id, validation_id, content_hash,
        )
        if row is None:
            current = await self.load(job_id)
            if current is None:
                raise CandidateNotFound(str(job_id))
            raise CandidateVersionConflict(
                f"候选内容已改变（hash={current['content_hash'][:12]}…），这次验证不绑定"
            )
        return _parse(row)  # type: ignore[arg-type]

    async def freeze(self, job_id: UUID, *, content_hash: str) -> dict[str, Any]:
        """冻结：之后的构建、验证、发布只认这一版内容。"""
        row = await self.conn.fetchrow(
            """update experiment_candidates
                  set status = 'frozen', updated_at = now()
                where job_id = $1 and content_hash = $2
                returning """ + CANDIDATE_COLUMNS,
            job_id, content_hash,
        )
        if row is None:
            current = await self.load(job_id)
            if current is None:
                raise CandidateNotFound(str(job_id))
            raise CandidateVersionConflict("候选在冻结前又被改了")
        return _parse(row)  # type: ignore[arg-type]

    async def attach_trace(self, job_id: UUID, *, trace: dict) -> None:
        """执行台账落库：审计用，不参与业务判定（业务状态只在 native_data/teaching_views）。"""
        r = await self.conn.execute(
            "update experiment_candidates set agent_trace = $2::jsonb, updated_at = now() where job_id = $1",
            job_id, json.dumps(trace, ensure_ascii=False),
        )
        if not r.endswith("1"):
            raise CandidateNotFound(str(job_id))

    async def set_status(self, job_id: UUID, *, status: str) -> None:
        r = await self.conn.execute(
            "update experiment_candidates set status = $2, updated_at = now() where job_id = $1",
            job_id, status,
        )
        if not r.endswith("1"):
            raise CandidateNotFound(str(job_id))

    async def rebase(self, job_id: UUID, *, revision_id: UUID) -> None:
        """发布成功后把候选的基线推进到刚发布的那一版。

        内容一个字节都不改，只是让「继续编辑」有一个诚实的基础版本——
        连续编辑链里第二次发布不能还拿最初的 base 去撞乐观并发。
        """
        r = await self.conn.execute(
            """update experiment_candidates
                  set base_revision = $2, status = 'editing', updated_at = now()
                where job_id = $1""",
            job_id, revision_id,
        )
        if not r.endswith("1"):
            raise CandidateNotFound(str(job_id))

    async def _explain_failure(self, job_id: UUID, expected_version: int) -> None:
        """CAS 失败要说清是「没有这一行」还是「被人改过」，否则排查只能猜。"""
        current = await self.load(job_id)
        if current is None:
            raise CandidateNotFound(str(job_id))
        raise CandidateVersionConflict(
            f"state_version 期望 {expected_version}，实际 {current['state_version']}"
        )
