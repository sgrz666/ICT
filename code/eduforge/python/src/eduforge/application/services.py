"""应用服务层聚合入口（§1.2）。

为向后兼容保留整体导入，具体职责分别在：
- application/job_service.py：任务生命周期
- application/experiment_service.py：模板与版本管理
- application/coordinator.py：Worker 流转编排
- application/publication.py：发布门禁
"""
from __future__ import annotations

from eduforge.application.experiment_service import (
    ActiveJobConflict,
    ExperimentLookup,
    ExperimentNotFound,
    ExperimentService,
    RevisionNotFound,
    TemplateNotFound,
)
from eduforge.application.job_service import (
    BaseNotHead,
    ExperimentNotOwned,
    JobService,
    RevisionNotOfExperiment,
)

__all__ = [
    "ExperimentService",
    "ExperimentLookup",
    "ExperimentNotFound",
    "TemplateNotFound",
    "RevisionNotFound",
    "ActiveJobConflict",
    "JobService",
    # Gate B §B.5：提交前的归属与基础版本核对，错误类型要在 API 层映射成 HTTP 语义
    "ExperimentNotOwned",
    "RevisionNotOfExperiment",
    "BaseNotHead",
]
