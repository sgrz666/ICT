"""Session projection registry and query service (@deepseek-ai/dsh-session-projection, @deepseek-ai/dsh-session-stats, @deepseek-ai/dsh-session-turn-outline, @deepseek-ai/dsh-session-query, @deepseek-ai/dsh-session-log-export).

Provides typed fold units over the immutable Format v4 event log (`state_of`, `snapshot`)
with incremental sequence caching, built-in `sessionStats` and `turnOutline` projections,
and event search/read/export utilities.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

from pydantic import BaseModel, Field

from .models import SessionEvent

if TYPE_CHECKING:
    from .state_machine import Session

T = TypeVar("T")


@dataclass
class ProjectionUnit(Generic[T]):
    """Definition of a single fold projection over SessionEvent streams."""

    key: str
    initial_factory: Callable[[], T]
    reducer: Callable[[T, SessionEvent], T]


class SessionStats(BaseModel):
    """Whole-log conversation counts and timing projection (`sessionStats`)."""

    turns: int = 0
    steps: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    tool_calls: int = 0
    tool_results: int = 0
    compactions: int = 0
    first_event_time: float | None = None
    last_event_time: float | None = None

    @property
    def wall_time_ms(self) -> float:
        if self.first_event_time is None or self.last_event_time is None:
            return 0.0
        return round(max(0.0, (self.last_event_time - self.first_event_time) * 1000.0), 2)


class TurnOutlineEntry(BaseModel):
    """Summary entry for a single turn in the `turnOutline` projection."""

    turn: int
    start_seq: int
    end_seq: int | None = None
    user_preview: str = ""
    steps_count: int = 0
    tool_names: list[str] = Field(default_factory=list)


class TurnBoundaryState(BaseModel):
    """Shared turn boundary fold state (`turnBoundary`)."""

    current_turn: int = 0
    current_step: int = 0
    in_turn: bool = False
    in_step: bool = False
    last_turn_end_seq: int | None = None


def _reduce_session_stats(state: SessionStats, event: SessionEvent) -> SessionStats:
    if state.first_event_time is None:
        state.first_event_time = event.time
    state.last_event_time = event.time

    etype = event.type
    if etype == "turn/start":
        state.turns += 1
    elif etype == "step/start":
        state.steps += 1
    elif etype == "user/message":
        state.user_messages += 1
    elif etype == "assistant/message":
        state.assistant_messages += 1
        tcs = event.data.get("tool_calls") or []
        state.tool_calls += len(tcs)
    elif etype == "tool/call":
        state.tool_calls += 1
    elif etype == "tool/result":
        state.tool_results += 1
    elif etype == "compaction/summary":
        state.compactions += 1
    return state


def _reduce_turn_outline(state: list[TurnOutlineEntry], event: SessionEvent) -> list[TurnOutlineEntry]:
    etype = event.type
    if etype == "turn/start":
        turn_no = int(event.data.get("turn", len(state) + 1))
        state.append(TurnOutlineEntry(turn=turn_no, start_seq=event.seq))
    elif etype == "user/message":
        if not state:
            state.append(TurnOutlineEntry(turn=1, start_seq=event.seq))
        if not state[-1].user_preview:
            raw_content = str(event.data.get("content", "")).strip()
            state[-1].user_preview = raw_content[:120]
    elif etype == "step/start":
        if state:
            state[-1].steps_count += 1
    elif etype == "assistant/message":
        if state:
            for tc in event.data.get("tool_calls") or []:
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                name = fn.get("name") or tc.get("name")
                if name and name not in state[-1].tool_names:
                    state[-1].tool_names.append(str(name))
    elif etype == "turn/end":
        if state:
            state[-1].end_seq = event.seq
    return state


def _reduce_turn_boundary(state: TurnBoundaryState, event: SessionEvent) -> TurnBoundaryState:
    etype = event.type
    if etype == "turn/start":
        state.current_turn = int(event.data.get("turn", state.current_turn + 1))
        state.current_step = 0
        state.in_turn = True
    elif etype == "step/start":
        state.current_step = int(event.data.get("step", state.current_step + 1))
        state.in_step = True
    elif etype == "step/end":
        state.in_step = False
    elif etype == "turn/end":
        state.in_turn = False
        state.in_step = False
        state.last_turn_end_seq = event.seq
    return state


class SessionProjectionRegistry:
    """Extensible fold projection registry with incremental per-session caching."""

    def __init__(self, register_defaults: bool = True):
        self._units: dict[str, ProjectionUnit[Any]] = {}
        # Cache keyed by (session_id, projection_key) -> (next_seq_to_fold, state)
        self._cache: dict[tuple[str, str], tuple[int, Any]] = {}
        if register_defaults:
            self.register("sessionStats", SessionStats, _reduce_session_stats)
            self.register("turnOutline", list, _reduce_turn_outline)
            self.register("turnBoundary", TurnBoundaryState, _reduce_turn_boundary)

    def register(
        self,
        key: str,
        initial_factory: Callable[[], T],
        reducer: Callable[[T, SessionEvent], T],
    ) -> None:
        """Register a named fold projection unit."""
        self._units[key] = ProjectionUnit(
            key=key,
            initial_factory=initial_factory,
            reducer=reducer,
        )

    def state_of(self, session: Session, key: str) -> Any:
        """Compute or incrementally update the projection state for `key` on `session`."""
        if key not in self._units:
            raise KeyError(f"Unknown session projection key: {key!r}")

        unit = self._units[key]
        cache_key = (session.session_id, key)
        cached = self._cache.get(cache_key)

        if cached is None or cached[0] > len(session.log):
            start_idx = 0
            state = unit.initial_factory()
        else:
            start_idx, state = cached

        for idx in range(start_idx, len(session.log)):
            state = unit.reducer(state, session.log[idx])

        self._cache[cache_key] = (len(session.log), state)
        return copy.deepcopy(state)

    def snapshot(self, session: Session) -> dict[str, Any]:
        """Compute all registered projections for `session`."""
        return {key: self.state_of(session, key) for key in self._units}


class SessionQueryService:
    """Search, slice-read, and export operations over Session logs (@deepseek-ai/dsh-session-query)."""

    @staticmethod
    def search_events(
        session: Session,
        query: str,
        event_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[SessionEvent]:
        """Search session events by case-insensitive substring or regex pattern."""
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        matches: list[SessionEvent] = []
        for ev in session.log:
            if event_types and ev.type not in event_types:
                continue
            haystack = f"{ev.type} {ev.data}"
            if pattern.search(haystack):
                matches.append(ev)
                if len(matches) >= limit:
                    break
        return matches

    @staticmethod
    def read_events(
        session: Session,
        start_seq: int = 0,
        count: int = 20,
    ) -> list[SessionEvent]:
        """Read a contiguous slice of events from `session.log`."""
        start = max(0, start_seq)
        end = min(len(session.log), start + max(1, count))
        return list(session.log[start:end])

    @staticmethod
    def export_markdown(session: Session) -> str:
        """Export session transcript and metadata as a structured Markdown document."""
        lines = [
            f"# Session Transcript: `{session.session_id}`",
            "",
            f"- **Format Version**: {session.header.version}",
            f"- **Working Directory**: `{session.cwd}`",
            f"- **Total Events**: {len(session.log)}",
            f"- **Active Surface Nodes**: {len(session.surface_manager.get_active_seqs())}",
            "",
            "## Active Model Surface",
            "",
        ]
        for idx, msg in enumerate(session.derive_messages(), start=1):
            lines.append(f"### [{idx}] Role: `{msg.role}`")
            if msg.content:
                lines.append(msg.content)
            if msg.tool_calls:
                lines.append(f"- **Tool Calls**: `{msg.tool_calls}`")
            lines.append("")
        return "\n".join(lines)
