"""Tool registry and built-in model tool suite for dsh-core (@deepseek-ai/dsh-tools).

Provides the 3-stage `pre-execute -> execute -> post-execute` tool pipeline
and registers all 28+ built-in filesystem, sandbox, job, autonomy, skill,
subagent, interaction, and physics LabKit tools.
"""

from .builtin_tools import register_builtin_tools
from .registry import (
    PostExecuteHook,
    PreExecuteHook,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionResult,
    ToolRegistry,
)

__all__ = [
    "ToolCallRequest",
    "ToolExecutionResult",
    "ToolDefinition",
    "ToolRegistry",
    "PreExecuteHook",
    "PostExecuteHook",
    "register_builtin_tools",
]
