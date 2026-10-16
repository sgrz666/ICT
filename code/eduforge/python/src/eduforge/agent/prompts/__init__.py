"""智能体系统提示词资源。

提示词与代码同库、按文件存放，便于逐字核对与版本追溯；
不写进 .py 字符串是为了让「模型被要求遵守什么」这件事可读、可 diff。
"""
from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent
EXPERIMENT_AGENT_PROMPT = _HERE / "experiment_agent.md"


def load_experiment_prompt() -> str:
    return EXPERIMENT_AGENT_PROMPT.read_text(encoding="utf-8")


__all__ = ["EXPERIMENT_AGENT_PROMPT", "load_experiment_prompt"]
