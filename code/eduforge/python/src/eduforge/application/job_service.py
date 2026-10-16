"""任务提交、幂等和取消服务。

对齐方案 §1.2：
- 职责单一：专门负责教师端提交异步任务、防重复幂等控制和任务取消。
"""
from __future__ import annotations

import uuid
import asyncpg

from eduforge.domain.contracts import CreateJobRequest, JobAccepted
from eduforge.infrastructure.db.repositories import JobRepository


class JobService:
    """任务生命周期管理服务。"""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.repo = JobRepository(conn)

    async def submit(self, *, owner_id: str, idempotency_key: uuid.UUID, body: CreateJobRequest) -> JobAccepted:
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

    async def get(self, job_id: uuid.UUID) -> dict | None:
        row = await self.conn.fetchrow(
            "select id, status, stage, error_code, candidate_revision_id from jobs where id = $1",
            job_id,
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
