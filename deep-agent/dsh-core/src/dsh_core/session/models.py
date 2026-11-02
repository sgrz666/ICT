"""Session event models, message schemas, and versioning.

Implements the official format version 4 event-sourced log specification from
DeepSeek Harness, including surface operations, turns, steps, and tool bindings.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

SESSION_FORMAT_VERSION: int = 4

Role = Literal["system", "developer", "user", "assistant", "tool"]
TurnEndReason = Literal["completed", "aborted", "blocked", "error", "max-tokens", "interrupted", "forked"]
SurfaceOpType = Literal["append", "replace"]

SURFACE_EVENT_TYPES: set[str] = {
    "system/message",
    "developer/message",
    "user/message",
    "assistant/message",
    "tool/result",
}


class SurfaceOp(BaseModel):
    """Specification of how an event modifies the model-visible surface."""

    op: SurfaceOpType = "append"
    start_seq: int | None = None
    end_seq: int | None = None


class ToolCall(BaseModel):
    """Structured tool call issued by an assistant."""

    id: str
    name: str
    arguments: str


class ToolResult(BaseModel):
    """Execution output of a tool call."""

    call_id: str
    name: str
    content: str
    is_error: bool = False


class Message(BaseModel):
    """Model-visible message formatted for LLM consumption."""

    role: Role
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to standard OpenAI-style message dictionary."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        return d


class SessionHeader(BaseModel):
    """Immutable header for a version 4 session log."""

    type: Literal["session"] = "session"
    version: int = SESSION_FORMAT_VERSION
    id: str
    created_at: float = Field(default_factory=time.time)
    cwd: str | None = None
    parent_session: str | None = None
    is_seeded: bool = False
    delegation_depth: int = 0


class SessionEvent(BaseModel):
    """A discrete, immutable event within the append-only session log."""

    seq: int
    type: str
    time: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)
    surface_op: SurfaceOp | None = None
    source_event_seqs: list[int] | None = None
    ignorable: bool = False

    def is_surface_eligible(self) -> bool:
        """Return True if this event is eligible for model-visible surface projection."""
        return self.type in SURFACE_EVENT_TYPES

    def to_model_message(self) -> Message | None:
        """Convert event data to a model-visible Message instance, or None if not applicable."""
        if not self.is_surface_eligible():
            return None

        if self.type == "system/message":
            return Message(
                role="system",
                content=self.data.get("content", ""),
            )
        elif self.type == "developer/message":
            return Message(
                role="developer",
                content=self.data.get("content", ""),
            )
        elif self.type == "user/message":
            return Message(
                role="user",
                content=self.data.get("content", ""),
            )
        elif self.type == "assistant/message":
            raw_calls = self.data.get("tool_calls", [])
            tool_calls = [
                ToolCall(
                    id=c.get("id", ""),
                    name=c.get("name") or c.get("function", {}).get("name", ""),
                    arguments=c.get("arguments") or c.get("function", {}).get("arguments", "{}"),
                )
                for c in raw_calls
            ] if raw_calls else None

            return Message(
                role="assistant",
                content=self.data.get("content", ""),
                tool_calls=tool_calls,
            )
        elif self.type == "tool/result":
            return Message(
                role="tool",
                content=self.data.get("content", self.data.get("output", "")),
                tool_call_id=self.data.get("call_id"),
                name=self.data.get("name"),
            )

        return None


class Turn(BaseModel):
    """Representation of an agent turn lifecycle."""

    turn_number: int
    status: Literal["running", "completed", "aborted", "error"] = "running"
    start_time: float = Field(default_factory=time.time)
    end_time: float | None = None
    reason: TurnEndReason | None = None
    steps: list[int] = Field(default_factory=list)


class Step(BaseModel):
    """Representation of a single step within an agent turn."""

    turn_number: int
    step_number: int
    status: Literal["running", "completed", "error"] = "running"
    start_time: float = Field(default_factory=time.time)
    end_time: float | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
