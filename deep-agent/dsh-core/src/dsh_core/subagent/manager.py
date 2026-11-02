"""In-process subagent delegation manager (@deepseek-ai/dsh-subagent, @deepseek-ai/dsh-subagent-spawn-in-process, @deepseek-ai/dsh-subagent-fork-in-process, @deepseek-ai/dsh-tool-subagent-control).

Provides both:
- `spawn`: fresh isolated child session starting from sequence 0;
- `fork`: child session seeded with the parent's `completed_turn_prefix` (all events
  up to and including the last `turn/end`) so the child inherits the parent's context
  and remains eligible for 100% KV-Cache prefix reuse.
Also provides `send_message`, `list_agents`, and `interrupt_agent` lifecycle controls.
"""

from __future__ import annotations

import copy
import uuid
from typing import Callable, Literal

from pydantic import BaseModel

from ..session.models import SessionEvent, SessionHeader
from ..session.state_machine import Session

SubagentMode = Literal["spawn", "fork"]
SubagentStatus = Literal["running", "completed", "interrupted", "failed"]


def completed_turn_prefix(parent_session: Session) -> list[SessionEvent]:
    """Return the balanced completed-turn prefix of `parent_session`'s log.

    Slices every event up to and including the last `turn/end`. The in-flight turn
    is excluded because an unfinished tool-call turn is unbalanced.
    """
    last_end_idx: int | None = None
    for idx in range(len(parent_session.log) - 1, -1, -1):
        if parent_session.log[idx].type == "turn/end":
            last_end_idx = idx
            break
    if last_end_idx is None:
        return []
    return [copy.deepcopy(ev) for ev in parent_session.log[: last_end_idx + 1]]


class SubagentSummary(BaseModel):
    """Serializable summary of a spawned or forked subagent."""

    agent_id: str
    parent_session_id: str
    mode: SubagentMode
    role: str
    status: SubagentStatus
    depth: int = 1
    seed_length: int = 0
    total_events: int = 0
    last_result: str = ""


class SubagentRecord:
    """Live in-process subagent record holding its child Session."""

    def __init__(
        self,
        agent_id: str,
        parent_session_id: str,
        mode: SubagentMode,
        role: str,
        session: Session,
        depth: int = 1,
        seed_length: int = 0,
    ):
        self.agent_id = agent_id
        self.parent_session_id = parent_session_id
        self.mode = mode
        self.role = role
        self.session = session
        self.depth = depth
        self.seed_length = seed_length
        self.status: SubagentStatus = "running"
        self.last_result: str = ""

    def to_summary(self) -> SubagentSummary:
        return SubagentSummary(
            agent_id=self.agent_id,
            parent_session_id=self.parent_session_id,
            mode=self.mode,
            role=self.role,
            status=self.status,
            depth=self.depth,
            seed_length=self.seed_length,
            total_events=len(self.session.log),
            last_result=self.last_result,
        )


class SubagentManager:
    """Registry and execution coordinator for `spawn` and `fork` subagents."""

    def __init__(
        self,
        max_depth: int = 3,
        default_runner: Callable[[Session, str], str] | None = None,
    ):
        self.max_depth = max(1, max_depth)
        self.default_runner = default_runner
        self._records: dict[str, SubagentRecord] = {}
        self._session_depths: dict[str, int] = {}

    def get_depth(self, session_id: str) -> int:
        return self._session_depths.get(session_id, 0)

    def _create_child_record(
        self,
        parent_session: Session,
        mode: SubagentMode,
        role: str,
        seed_events: list[SessionEvent],
    ) -> SubagentRecord:
        parent_depth = self.get_depth(parent_session.session_id)
        child_depth = parent_depth + 1
        if child_depth > self.max_depth:
            raise PermissionError(
                f"Subagent recursion depth limit exceeded ({child_depth} > max_depth={self.max_depth})"
            )

        agent_id = f"sub_{mode}_{uuid.uuid4().hex[:8]}"
        header = SessionHeader(id=agent_id, cwd=parent_session.cwd)
        child_session = Session(session_id=agent_id, cwd=parent_session.cwd, header=header)

        for ev in seed_events:
            child_session.log.append(ev)
            child_session.surface_manager.apply(ev)

        self._session_depths[agent_id] = child_depth
        record = SubagentRecord(
            agent_id=agent_id,
            parent_session_id=parent_session.session_id,
            mode=mode,
            role=role,
            session=child_session,
            depth=child_depth,
            seed_length=len(seed_events),
        )
        self._records[agent_id] = record
        return record

    def _execute_task(
        self,
        record: SubagentRecord,
        prompt: str,
        runner_fn: Callable[[Session, str], str] | None = None,
    ) -> SubagentSummary:
        active_runner = runner_fn or self.default_runner
        record.status = "running"

        try:
            if active_runner is not None:
                result_text = active_runner(record.session, prompt)
            else:
                record.session.append("turn/start", {"turn": 1})
                record.session.append("step/start", {"turn": 1, "step": 1})
                record.session.append(
                    "user/message",
                    {"role": "user", "content": prompt},
                    surface_op="append",
                )
                result_text = f"[{record.role} ({record.mode})] Completed task: {prompt[:120]}"
                record.session.append(
                    "assistant/message",
                    {"role": "assistant", "content": result_text},
                    surface_op="append",
                )
                record.session.append("step/end", {"turn": 1, "step": 1})
                record.session.append("turn/end", {"turn": 1, "reason": "complete"})

            record.last_result = result_text
            if record.status == "running":
                record.status = "completed"
        except Exception as exc:
            record.status = "failed"
            record.last_result = f"Subagent failed: {exc}"

        return record.to_summary()

    def spawn(
        self,
        parent_session: Session,
        role: str,
        prompt: str,
        runner_fn: Callable[[Session, str], str] | None = None,
    ) -> SubagentSummary:
        """Spawn a fresh child subagent with an empty initial log (`subagent`)."""
        record = self._create_child_record(
            parent_session=parent_session,
            mode="spawn",
            role=role,
            seed_events=[],
        )
        return self._execute_task(record, prompt, runner_fn=runner_fn)

    def fork(
        self,
        parent_session: Session,
        role: str,
        prompt: str,
        runner_fn: Callable[[Session, str], str] | None = None,
    ) -> SubagentSummary:
        """Fork a child subagent seeded with the parent's `completed_turn_prefix` (`subagent_fork`)."""
        seed = completed_turn_prefix(parent_session)
        record = self._create_child_record(
            parent_session=parent_session,
            mode="fork",
            role=role,
            seed_events=seed,
        )
        return self._execute_task(record, prompt, runner_fn=runner_fn)

    def send_message(
        self,
        agent_id: str,
        message: str,
        runner_fn: Callable[[Session, str], str] | None = None,
    ) -> SubagentSummary:
        """Send a follow-up prompt to an existing subagent (`send_message`)."""
        record = self._records.get(agent_id)
        if record is None:
            raise KeyError(f"Unknown subagent id: {agent_id!r}")
        if record.status == "interrupted":
            raise RuntimeError(f"Cannot send_message to interrupted subagent {agent_id!r}")
        return self._execute_task(record, message, runner_fn=runner_fn)

    def interrupt_agent(self, agent_id: str) -> SubagentSummary:
        """Interrupt a subagent (`interrupt_agent`)."""
        record = self._records.get(agent_id)
        if record is None:
            raise KeyError(f"Unknown subagent id: {agent_id!r}")
        record.status = "interrupted"
        return record.to_summary()

    def list_agents(self, parent_session_id: str | None = None) -> list[SubagentSummary]:
        """List registered subagents, optionally filtered by parent session (`list_agents`)."""
        records = list(self._records.values())
        if parent_session_id is not None:
            records = [r for r in records if r.parent_session_id == parent_session_id]
        return [r.to_summary() for r in records]

    def get_record(self, agent_id: str) -> SubagentRecord:
        if agent_id not in self._records:
            raise KeyError(f"Unknown subagent id: {agent_id!r}")
        return self._records[agent_id]
