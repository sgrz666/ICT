"""任务级错误分类。

放在独立模块是为了让 Worker 与各阶段步骤共用同一词汇而不互相 import：
终态（TerminalError、策略 Rejected）写 failed，非终态留给别的 Worker 接管。
"""
from __future__ import annotations


class TerminalError(Exception):
    """这条任务不可能成功：不再重试，直接落到 failed 并带 error_code。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
