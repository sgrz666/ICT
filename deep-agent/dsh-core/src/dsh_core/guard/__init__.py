"""Guard subsystem for dsh-core (@deepseek-ai/dsh-repeat-tool-reminder & @deepseek-ai/dsh-tool-call-timeout-policy).

Provides repeat tool-call detection with gentle-to-detailed reminder escalation
and per-tool execution deadline policies.
"""

from .repeat_reminder import (
    GENTLE_REMINDER,
    RepeatToolReminder,
    canonicalize_arguments,
    detailed_reminder,
)
from .timeout_policy import ToolCallTimeoutError, ToolTimeoutPolicy

__all__ = [
    "RepeatToolReminder",
    "GENTLE_REMINDER",
    "detailed_reminder",
    "canonicalize_arguments",
    "ToolTimeoutPolicy",
    "ToolCallTimeoutError",
]
