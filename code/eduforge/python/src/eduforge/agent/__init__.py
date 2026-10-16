"""EduForge 智能体模块。

规则式 `ExperimentToolAgent` 已删除：它的意图解析是正则、修复靠伪造验证记录，
执行核心由 `deepagents_runtime` 承接。这里刻意不在包导入时拉起运行时依赖，
避免 `experiment_tools` 与本包互相引用形成循环。
"""
from __future__ import annotations

from eduforge.agent.bootstrap import build_planner

__all__ = ["build_planner"]
