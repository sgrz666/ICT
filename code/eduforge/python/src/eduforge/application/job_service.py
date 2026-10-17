"""任务提交、幂等、取消与查询服务。

对齐方案 §1.2 与 §6.1。Gate B §B.5 起，这一层还要负责**归属**：

- 提交时核对实验属于当前身份、`base_revision` 确实属于该实验、并且是被允许的
  head——否则教师的一句「在某个版本上改」能让任务落到别人的或过期的场景上；
- 查询与取消一律按身份限定，不能只按 job id 放行。

固定开发身份（`local-dev`）只是本地演练的入口，不是认证；生产必须换成真实身份注入。
"""
from __future__ import annotations

import uuid

import asyncpg

from eduforge.domain.contracts import CreateJobRequest, JobAccepted
from eduforge.domain.errors import ConflictError, NotFoundError
from eduforge.infrastructure.db.repositories import JobRepository


class ExperimentNotOwned(NotFoundError):
    """实验不存在，或不属于当前身份。

    两种情况故意给同一个错误：存在性本身是别人的信息，不能靠 404/403 的差别试探出来。
    """


class RevisionNotOfExperiment(ConflictError):
    """给定的 base_revision 不属于这个实验。"""


class BaseNotHead(ConflictError):
    """base_revision 不是该实验当前允许的基础版本（教师已经产生新版本）。"""


class JobService:
    """任务生命周期管理服务。"""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.repo = JobRepository(conn)

    async def assert_submittable(
        self, *, owner_id: str, experiment_id: uuid.UUID, base_revision: uuid.UUID
    ) -> None:
        exp = await self.conn.fetchrow(
            "select id, owner_id, head_revision_id from experiments where id = $1", experiment_id
        )
        if exp is None or str(exp["owner_id"]) != str(owner_id):
            raise ExperimentNotOwned(str(experiment_id))
        rev = await self.conn.fetchval(
            "select 1 from experiment_revisions where id = $1 and experiment_id = $2",
            base_revision, experiment_id,
        )
        if rev is None:
            raise RevisionNotOfExperiment(
                f"版本 {base_revision} 不属于实验 {experiment_id}"
            )
        # 允许的基础版本就是当前 head：任务落在过期版本上时，发布事务的乐观并发
        # 会在几分钟后才失败，教师看到的是「跑了一半白干」。在这里就拒掉。
        if exp["head_revision_id"] is not None and str(exp["head_revision_id"]) != str(base_revision):
            raise BaseNotHead(
                f"实验 {experiment_id} 的当前版本是 {exp['head_revision_id']}，不能基于 {base_revision} 提交"
            )

    async def submit(
        self, *, owner_id: str, idempotency_key: uuid.UUID, body: CreateJobRequest
    ) -> JobAccepted:
        await self.assert_submittable(
            owner_id=owner_id, experiment_id=body.experiment_id, base_revision=body.base_revision
        )
        row = await self.repo.create_job(
            job_id=uuid.uuid4(),
            owner_id=owner_id,
            experiment_id=body.experiment_id,
            base_revision=body.base_revision,
            prompt=body.prompt,
            idempotency_key=idempotency_key,
        )
        return JobAccepted(job_id=row["id"], status=row["status"])

    async def cancel(self, *, owner_id: str, job_id: uuid.UUID) -> str | None:
        return await self.repo.cancel(job_id, owner_id)

    async def get(self, job_id: uuid.UUID, *, owner_id: str) -> dict | None:
        """按身份取任务：别人的 job 在这里等于不存在。"""
        row = await self.conn.fetchrow(
            "select id, status, stage, error_code, candidate_revision_id from jobs "
            "where id = $1 and owner_id = $2",
            job_id, owner_id,
        )
        if row is None:
            return None
        events = await self.repo.events(job_id)
        return {
            "job_id": row["id"],
            "status": row["status"],
            "stage": row["stage"],
            "error_code": row["error_code"],
            "candidate_revision_id": row["candidate_revision_id"],
            "events": [
                {"sequence": e["sequence"], "stage": e["stage"], "event_type": e["event_type"]}
                for e in events
            ],
        }
