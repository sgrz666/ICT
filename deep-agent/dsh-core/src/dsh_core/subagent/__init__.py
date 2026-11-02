"""Subagent delegation subsystem for dsh-core (@deepseek-ai/dsh-subagent, @deepseek-ai/dsh-subagent-spawn-in-process, @deepseek-ai/dsh-subagent-fork-in-process).

Provides fresh-session `spawn` delegation, KV-cache-reusing `fork` delegation
seeded with `completed_turn_prefix`, and subagent control primitives
(`send_message`, `list_agents`, `interrupt_agent`).
"""

from .manager import (
    SubagentManager,
    SubagentMode,
    SubagentRecord,
    SubagentStatus,
    SubagentSummary,
    completed_turn_prefix,
)

__all__ = [
    "SubagentMode",
    "SubagentStatus",
    "SubagentSummary",
    "SubagentRecord",
    "SubagentManager",
    "completed_turn_prefix",
]
