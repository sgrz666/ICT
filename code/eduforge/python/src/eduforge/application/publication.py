"""发布：只有验证结论为 passed 的报告才允许把候选版本推上 head。

§3.5 的四道闸门都在 JobRepository.publish 的一条 UPDATE 里；这里加的是
"报告必须存在且 verdict=passed"这条业务前置，二者叠加才构成发布门禁。
"""
from __future__ import annotations

import json
import uuid

import asyncpg

from eduforge.infrastructure.db.repositories import JobRepository
from eduforge.validation.reports import ValidationReport


class NotPublishable(Exception):
    def __init__(self, reason: str, report: ValidationReport | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.report = report


class Publisher:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.repo = JobRepository(conn)

    async def record_report(self, *, job_id: uuid.UUID, report: ValidationReport) -> uuid.UUID:
        rid = uuid.uuid4()
        await self.conn.execute(
            "insert into validation_reports (id, job_id, checks, verdict) values ($1,$2,$3::jsonb,$4)",
            rid, job_id, json.dumps(report.as_dict()), report.verdict,
        )
        return rid

    async def publish(
        self,
        *,
        job_id: uuid.UUID,
        lease_token: str,
        experiment_id: uuid.UUID,
        base_revision: uuid.UUID,
        candidate_revision_id: uuid.UUID,
        native_data: dict,
        report_verdict: str,
        artifacts: list[dict] | None = None,
        cancelled: bool = False,
        lesson: dict | None = None,
        bindings: dict | None = None,
    ) -> None:
        if report_verdict != "passed":
            # 失败或没验过的任务，不得发布为成功资源（§7.5 的项目方法比较目标之一）
            raise NotPublishable(f"verdict={report_verdict}")
        await self.repo.publish(
            job_id=job_id,
            lease_token=lease_token,
            experiment_id=experiment_id,
            base_revision=base_revision,
            candidate_revision_id=candidate_revision_id,
            native_data=native_data,
            checks_passed=True,
            artifacts=artifacts,
            cancelled=cancelled,
            lesson=lesson,
            bindings=bindings,
        )
