"""EduForge 领域核心层（Domain Layer）。

按照方案 §1.2 规定：纯核心，不依赖外部框架。
提供 models、contracts、ports、errors 的标准导出。
"""
from eduforge.domain import errors, models, ports
from eduforge.domain.contracts import (
    Contract,
    EditProposal,
    Operation,
    PlannerRequest,
    SetParameter,
    SetView,
    WorkOrder,
)
from eduforge.domain.errors import (
    ConflictError,
    EduForgeError,
    LeaseExpiredError,
    NotFoundError,
    PolicyViolationError,
    ScientificValidationError,
)
from eduforge.domain.models import (
    Artifact,
    Experiment,
    ExperimentRevision,
    Job,
    JobEvent,
    ValidationReport,
)

__all__ = [
    "errors",
    "models",
    "ports",
    "Contract",
    "EditProposal",
    "Operation",
    "SetParameter",
    "SetView",
    "PlannerRequest",
    "WorkOrder",
    "EduForgeError",
    "PolicyViolationError",
    "ConflictError",
    "NotFoundError",
    "LeaseExpiredError",
    "ScientificValidationError",
    "Experiment",
    "ExperimentRevision",
    "Job",
    "Artifact",
    "ValidationReport",
    "JobEvent",
]
