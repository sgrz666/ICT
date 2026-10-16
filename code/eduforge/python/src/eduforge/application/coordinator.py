"""任务推进：阶段机 + 崩溃后从保存的 stage 恢复。

阶段的完成与否以 job_events 为准，不看内存里的循环变量——重启后内存清空，
唯一可信的是数据库里已经落下的事件。
"""
from __future__ import annotations

from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from uuid import UUID

from eduforge.infrastructure.db.repositories import JobRepository

STAGES = ["planning", "editing", "building", "validating", "packaging"]

Step = Callable[[UUID], Awaitable[dict]]


@dataclass
class Coordinator:
    repo: JobRepository
    steps: dict[str, Step]

    async def completed_stages(self, job_id: UUID) -> set[str]:
        rows = await self.repo.conn.fetch(
            "select distinct stage from job_events where job_id = $1 and event_type = 'stage_done'",
            job_id,
        )
        return {r["stage"] for r in rows if r["stage"]}

    async def run(self, job_id: UUID, lease_token: str) -> str:
        """从第一个未完成的阶段接着走。返回最后完成的阶段。"""
        done = await self.completed_stages(job_id)
        last = None
        for stage in STAGES:
            if stage in done:
                last = stage
                continue
            await self.repo.set_stage(job_id, lease_token, stage)
            await self.repo.append_event(job_id, stage=stage, event_type="stage_start")
            payload = await self.steps[stage](job_id)
            await self.repo.append_event(
                job_id, stage=stage, event_type="stage_done", payload=payload
            )
            last = stage
        return last
