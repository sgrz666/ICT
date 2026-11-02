"""Session and dialogue subsystem for dsh-core.

Implements format version 4 event-sourced logs, surface projections, agent React
loops with inbox claiming, atomic JSONL persistence, and pluggable LLM clients.
"""

from .llm_client import BaseLlmClient, MockLlmClient, OpenAiCompatibleClient
from .models import (
    SESSION_FORMAT_VERSION,
    Message,
    Role,
    SessionEvent,
    SessionHeader,
    Step,
    SurfaceOp,
    ToolCall,
    ToolResult,
    Turn,
    TurnEndReason,
)
from .persistence import JsonlPersistence, encode_session_id, project_key
from .projection import (
    ProjectionUnit,
    SessionProjectionRegistry,
    SessionQueryService,
    SessionStats,
    TurnBoundaryState,
    TurnOutlineEntry,
)
from .state_machine import ReactLoopInbox, ReactLoopState, Session
from .surface import SurfaceManager

__all__ = [
    "SESSION_FORMAT_VERSION",
    "Session",
    "SessionEvent",
    "SessionHeader",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
    "Turn",
    "Step",
    "TurnEndReason",
    "SurfaceOp",
    "SurfaceManager",
    "ProjectionUnit",
    "SessionProjectionRegistry",
    "SessionStats",
    "TurnOutlineEntry",
    "TurnBoundaryState",
    "SessionQueryService",
    "JsonlPersistence",
    "project_key",
    "encode_session_id",
    "ReactLoopInbox",
    "ReactLoopState",
    "BaseLlmClient",
    "MockLlmClient",
    "OpenAiCompatibleClient",
]
