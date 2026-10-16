"""代码定制的资源与执行预算控制。

对齐方案 §1.2 和 §4.6：
- 严格限制模型调用轮次、执行时长和代码修复预算；
- 防止智能体陷入无限死循环或消耗过度 token。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionBudget:
    """定制任务的执行预算。"""
    max_duration_seconds: int = 300  # 整体最长 5 分钟
    max_turns: int = 30             # 最多 30 轮调用
    max_repair_attempts: int = 3    # 自动编译/测试失败最多重试 3 次
    max_export_bytes: int = 10 * 1024 * 1024  # 导出产物上限 10MB
