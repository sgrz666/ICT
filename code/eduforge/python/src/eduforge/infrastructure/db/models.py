"""数据库表结构与 DDL 定义。

对齐方案 §1.2 和 §3.4 数据表设计。
"""
from __future__ import annotations

from eduforge.infrastructure.db.repositories import JOBS_DDL

TABLES = [
    "jobs",
    "experiments",
    "experiment_revisions",
    "artifacts",
    "validation_reports",
    "job_events",
]

__all__ = ["JOBS_DDL", "TABLES"]
