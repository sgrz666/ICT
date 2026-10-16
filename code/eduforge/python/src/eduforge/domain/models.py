"""EduForge 核心领域模型（Entities / Value Objects）。

对齐方案 §1.2 和 §3.4 数据表设计，纯领域对象，不耦合任何 ORM 或外部框架。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class Experiment:
    """实验聚合根。"""
    id: UUID
    owner_id: str
    template_id: str
    head_revision_id: UUID | None = None


@dataclass
class ExperimentRevision:
    """实验不可变版本。"""
    id: UUID
    experiment_id: UUID
    parent_id: UUID | None
    engine_id: str
    native_data: dict[str, Any]
    lesson: dict[str, Any] | None = None
    bindings: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Job:
    """异步任务实体。"""
    id: UUID
    owner_id: str
    experiment_id: UUID
    base_revision: UUID
    prompt: str | None
    status: str
    stage: str | None
    attempt: int
    idempotency_key: UUID
    request_hash: str
    lease_token: str | None = None
    lease_until: datetime | None = None
    next_run_at: datetime = field(default_factory=datetime.utcnow)
    candidate_revision_id: UUID | None = None
    work_order: dict[str, Any] | None = None
    error_code: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Artifact:
    """实验导出的静态/二进制制品。"""
    id: UUID
    revision_id: UUID
    storage_key: str
    sha256: str
    media_type: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ValidationReport:
    """验证报告实体。"""
    id: UUID
    job_id: UUID
    checks: list[dict[str, Any]]
    verdict: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobEvent:
    """任务时间线事件记录。"""
    job_id: UUID
    sequence: int
    stage: str | None
    event_type: str
    payload: dict[str, Any] | None
    created_at: datetime = field(default_factory=datetime.utcnow)
