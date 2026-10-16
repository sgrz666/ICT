"""EduForge 系统配置与环境变量管理。

对齐方案 §1.2：统一读取数据库、Engine Host、Agent 及存储参数。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    """系统运行配置。"""
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://eduforge:eduforge@127.0.0.1:5432/eduforge",
    )
    engine_host_url: str = os.getenv("ENGINE_HOST_URL", "http://127.0.0.1:4000")
    agent_host_url: str = os.getenv("AGENT_HOST_URL", "http://127.0.0.1:8001")
    artifacts_dir: Path = Path(os.getenv("ARTIFACTS_DIR", "output/eduforge/artifacts"))
    templates_dir: Path = Path(os.getenv("TEMPLATES_DIR", "catalog/templates"))
    deepseek_api_key: str | None = os.getenv("DEEPSEEK_API_KEY")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


settings = Settings()
