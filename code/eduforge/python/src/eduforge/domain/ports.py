"""EduForge 领域端口（抽象接口协议）。

对齐方案 §1.2，定义业务层对数据库、外部计算引擎、存储与 Agent 服务的依赖边界。
"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from eduforge.domain.contracts import PlannerRequest, WorkOrder
from eduforge.domain.models import (
    Artifact,
    Experiment,
    ExperimentRevision,
    Job,
    ValidationReport,
)


class JobRepositoryPort(Protocol):
    """任务仓储端口。"""

    async def submit_job(
        self,
        *,
        owner_id: str,
        experiment_id: UUID,
        base_revision: UUID,
        prompt: str,
        idempotency_key: UUID,
        request_hash: str,
    ) -> tuple[Job, bool]: ...

    async def acquire_job(self, *, lease_token: str, lease_seconds: int = 90) -> Job | None: ...

    async def heartbeat(self, *, job_id: UUID, lease_token: str, lease_seconds: int = 90) -> bool: ...

    async def complete_job(
        self,
        *,
        job_id: UUID,
        lease_token: str,
        candidate_revision_id: UUID,
        checks: list[dict[str, Any]],
    ) -> bool: ...

    async def fail_job(
        self,
        *,
        job_id: UUID,
        lease_token: str,
        error_code: str,
        checks: list[dict[str, Any]] | None = None,
    ) -> bool: ...

    async def cancel_job(self, *, job_id: UUID, owner_id: str) -> str: ...


class ExperimentRepositoryPort(Protocol):
    """实验与版本仓储端口。"""

    async def get_experiment(self, experiment_id: UUID) -> Experiment | None: ...

    async def get_revision(self, revision_id: UUID) -> ExperimentRevision | None: ...

    async def create_experiment(
        self,
        *,
        owner_id: str,
        template_id: str,
        engine_id: str,
        native_data: dict[str, Any],
        lesson: dict[str, Any] | None = None,
        bindings: dict[str, Any] | None = None,
    ) -> tuple[Experiment, ExperimentRevision]: ...

    async def rollback(self, *, experiment_id: UUID, target_revision_id: UUID, owner_id: str) -> bool: ...


class ArtifactStoragePort(Protocol):
    """产物持久化存储端口（本地文件系统 / OBS）。"""

    async def put(self, key: str, data: bytes, media_type: str) -> str: ...

    async def get(self, key: str) -> bytes | None: ...

    async def exists(self, key: str) -> bool: ...


class EngineClientPort(Protocol):
    """引擎宿主交互端口。"""

    async def patch_scene(self, *, engine_id: str, base_native: dict[str, Any], work_order: WorkOrder) -> dict[str, Any]: ...

    async def build_offline_package(self, *, scene: dict[str, Any], title: str | None = None) -> dict[str, Any]: ...


class AgentPlannerPort(Protocol):
    """规划智能体端口。"""

    async def plan(self, request: PlannerRequest) -> WorkOrder: ...
