"""Agent React loop state machine and session container.

Orchestrates turn/step transitions, claims incoming inbox messages, and causally
links tool calls with tool results in the append-only session log.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from .models import (
    Message,
    SessionEvent,
    SessionHeader,
    Step,
    SurfaceOp,
    ToolCall,
    ToolResult,
    Turn,
    TurnEndReason,
)
from .persistence import JsonlPersistence
from .surface import SurfaceManager


class Session:
    """Core Session managing event logs, surface projections, and persistence."""

    def __init__(
        self,
        session_id: str,
        cwd: str | None = None,
        header: SessionHeader | None = None,
        persistence: JsonlPersistence | None = None,
    ):
        self.id = session_id
        self.session_id = session_id
        self.cwd = cwd
        self.header = header or SessionHeader(id=session_id, cwd=cwd)
        self.log: list[SessionEvent] = []
        self.surface_manager = SurfaceManager()
        self.persistence = persistence

        # Initialize persistence file if empty and persistence provided
        if self.persistence and not self.persistence.exists():
            self.persistence.init_session(self.header)

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        surface_op: str | SurfaceOp = "append",
        replace_range: tuple[int, int] | None = None,
        source_event_seqs: list[int] | None = None,
        ignorable: bool = False,
    ) -> SessionEvent:
        """Append an event to the session log, update surface projection, and persist.

        Args:
            event_type: Event type name (e.g. 'user/message', 'tool/call').
            data: Payload dictionary for the event.
            surface_op: Surface operation: 'append' or SurfaceOp instance.
            replace_range: Optional tuple of (start_seq, end_seq) if replacing a surface range.
            source_event_seqs: Sequence numbers of causal ancestor events (e.g. tool call seq).
            ignorable: Whether the event can be ignored by downstream observers.

        Returns:
            The created SessionEvent instance.
        """
        seq = len(self.log)

        # Resolve SurfaceOp
        op: SurfaceOp | None = None
        if isinstance(surface_op, SurfaceOp):
            op = surface_op
        elif surface_op == "replace" or replace_range is not None:
            start_seq = replace_range[0] if replace_range else seq
            end_seq = replace_range[1] if replace_range else seq
            op = SurfaceOp(op="replace", start_seq=start_seq, end_seq=end_seq)
        elif surface_op == "append":
            op = SurfaceOp(op="append")

        event = SessionEvent(
            seq=seq,
            type=event_type,
            time=time.time(),
            data=data,
            surface_op=op,
            source_event_seqs=source_event_seqs,
            ignorable=ignorable,
        )

        self.log.append(event)
        self.surface_manager.apply(event)

        if self.persistence:
            self.persistence.append_event(event)

        return event

    def derive_messages(self) -> list[Message]:
        """Derive the current model-visible messages based on active surface nodes."""
        messages: list[Message] = []
        for seq in self.surface_manager.get_active_seqs():
            if seq < len(self.log):
                msg = self.log[seq].to_model_message()
                if msg is not None:
                    messages.append(msg)
        return messages

    def get_event(self, seq: int) -> SessionEvent:
        """Retrieve an event by sequence number."""
        return self.log[seq]

    def total_events(self) -> int:
        """Return total event count."""
        return len(self.log)

    @classmethod
    def restore(cls, persistence: JsonlPersistence) -> Session:
        """Reconstruct a Session from an existing persistence JSONL file."""
        header, events = persistence.load_session()
        session = cls(
            session_id=header.id,
            cwd=header.cwd,
            header=header,
            persistence=persistence,
        )

        for event in events:
            session.log.append(event)
            session.surface_manager.apply(event)

        return session


class ReactLoopInbox:
    """Manages pending user and system messages for upcoming turns and steps."""

    def __init__(self):
        self.next_turn_messages: list[Message] = []
        self.next_step_messages: list[Message] = []

    def push_user_message(self, content: str | Message, for_next_step: bool = False) -> None:
        """Enqueue a user message."""
        if isinstance(content, str):
            msg = Message(role="user", content=content)
        else:
            msg = content

        if for_next_step:
            self.next_step_messages.append(msg)
        else:
            self.next_turn_messages.append(msg)

    def pop_next_step(self) -> Message | None:
        """Pop an immediate step injection message if available."""
        if self.next_step_messages:
            return self.next_step_messages.pop(0)
        return None

    def pop_next_turn(self) -> Message | None:
        """Pop a message queued for the next turn."""
        if self.next_turn_messages:
            return self.next_turn_messages.pop(0)
        return None

    def has_pending(self) -> bool:
        """Check if any messages are pending in either queue."""
        return bool(self.next_turn_messages or self.next_step_messages)


class ReactLoopState:
    """Turn / Step agent loop lifecycle driver."""

    def __init__(self, session: Session, inbox: ReactLoopInbox | None = None):
        self.session = session
        self.inbox = inbox or ReactLoopInbox()
        self.phase: Literal["idle", "running", "maintenance"] = "idle"
        self.turn_index: int = 0
        self.step_index: int = 0
        self.current_turn: Turn | None = None
        self.current_step: Step | None = None

    def start_turn(self) -> Turn:
        """Begin a new agent turn."""
        self.turn_index += 1
        self.step_index = 0
        self.phase = "running"

        turn = Turn(turn_number=self.turn_index, status="running")
        self.current_turn = turn

        self.session.append(
            "turn/start",
            {"turn": self.turn_index},
        )
        return turn

    def end_turn(self, reason: TurnEndReason = "completed") -> Turn:
        """End the active turn."""
        if not self.current_turn:
            raise RuntimeError("Cannot end turn: no active turn.")

        self.current_turn.status = "completed" if reason == "completed" else "error"
        self.current_turn.end_time = time.time()
        self.current_turn.reason = reason
        self.phase = "idle"

        self.session.append(
            "turn/end",
            {"turn": self.turn_index, "reason": reason},
        )
        ended = self.current_turn
        self.current_turn = None
        return ended

    def start_step(self) -> Step:
        """Begin a new step within the active turn."""
        if not self.current_turn:
            self.start_turn()

        self.step_index += 1
        step = Step(
            turn_number=self.turn_index,
            step_number=self.step_index,
            status="running",
        )
        self.current_step = step
        self.current_turn.steps.append(self.step_index)

        self.session.append(
            "step/start",
            {"turn": self.turn_index, "step": self.step_index},
        )
        return step

    def end_step(self) -> Step:
        """End the current step."""
        if not self.current_step:
            raise RuntimeError("Cannot end step: no active step.")

        self.current_step.status = "completed"
        self.current_step.end_time = time.time()

        self.session.append(
            "step/end",
            {"turn": self.turn_index, "step": self.step_index},
        )
        ended = self.current_step
        self.current_step = None
        return ended

    def record_tool_call(
        self,
        name: str,
        arguments: str,
        call_id: str | None = None,
    ) -> SessionEvent:
        """Record an assistant tool invocation in the event log.

        Returns:
            The created 'tool/call' SessionEvent.
        """
        cid = call_id or f"call_{uuid.uuid4().hex[:8]}"
        tc = ToolCall(id=cid, name=name, arguments=arguments)

        if self.current_step:
            self.current_step.tool_calls.append(tc)

        return self.session.append(
            "tool/call",
            {
                "turn": self.turn_index,
                "step": self.step_index,
                "call_id": cid,
                "name": name,
                "arguments": arguments,
            },
        )

    def record_tool_result(
        self,
        call_event_seq: int,
        name: str,
        content: str,
        is_error: bool = False,
        call_id: str | None = None,
    ) -> SessionEvent:
        """Record tool output, causally linking it to its triggering tool/call event."""
        cid = call_id
        if not cid and call_event_seq < len(self.session.log):
            call_evt = self.session.log[call_event_seq]
            cid = call_evt.data.get("call_id", f"call_{call_event_seq}")
        cid = cid or f"call_{call_event_seq}"

        tr = ToolResult(call_id=cid, name=name, content=content, is_error=is_error)
        if self.current_step:
            self.current_step.tool_results.append(tr)

        return self.session.append(
            "tool/result",
            {
                "turn": self.turn_index,
                "step": self.step_index,
                "call_id": cid,
                "name": name,
                "content": content,
                "is_error": is_error,
            },
            surface_op="append",
            source_event_seqs=[call_event_seq],
        )
