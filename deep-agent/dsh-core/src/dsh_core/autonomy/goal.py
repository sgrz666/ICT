"""Same-session goal domain and automatic round driver (@deepseek-ai/dsh-goal & @deepseek-ai/dsh-goal-round-driver).

Implements event-sourced goal state (`active`, `paused`, `blocked`, `complete`),
Compare-And-Set (CAS) revision tracking, the official 3-round floor before a goal
may transition to `blocked` (`MIN_ROUNDS_BEFORE_BLOCK = 3`), and automatic
continuation prompt generation when a turn ends while the goal remains active.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..session.projection import SessionProjectionRegistry
    from ..session.state_machine import Session

GoalPhase = Literal["active", "paused", "blocked", "complete"]
GoalActivation = Literal["armed", "disarmed"]

# Official dsh rule: a goal cannot be marked `blocked` before at least 3 admitted rounds
MIN_ROUNDS_BEFORE_BLOCK: int = 3


class GoalError(ValueError):
    """Raised on invalid goal transitions, CAS revision mismatches, or blocked-floor violations."""


class GoalBlockReason(BaseModel):
    """Structured reason when a goal transitions to `blocked`."""

    code: str
    message: str


class GoalSnapshot(BaseModel):
    """Point-in-time goal specification."""

    id: str
    revision: int = 1
    objective: str
    phase: GoalPhase = "active"
    blocked_reason: GoalBlockReason | None = None
    max_goal_rounds: int = 20


class GoalView(BaseModel):
    """Complete view of a session's active goal state."""

    goal: GoalSnapshot
    rounds_started: int = 0
    created_at: float
    updated_at: float
    activation: GoalActivation = "armed"


def render_goal_round_prompt(view: GoalView, round_number: int) -> str:
    """Render the official automatic continuation prompt for a goal round."""
    return (
        f"[GOAL ROUND {round_number}/{view.goal.max_goal_rounds}]\n"
        f"Active Goal (id={view.goal.id}, rev={view.goal.revision}): {view.goal.objective}\n\n"
        "Audit your progress against the objective:\n"
        "- If the objective is completely fulfilled and verified, call `update_goal` with `phase='complete'`.\n"
        "- If work remains, execute the next concrete steps now.\n"
        f"- Note: transitioning to `phase='blocked'` requires at least {MIN_ROUNDS_BEFORE_BLOCK} completed rounds "
        f"(current rounds_started={round_number})."
    )


class GoalManager:
    """Event-sourced same-session goal service."""

    def __init__(self, projection_registry: SessionProjectionRegistry | None = None):
        self._views: dict[str, GoalView] = {}
        if projection_registry is not None:
            projection_registry.register("goal", lambda: None, self._reduce_goal)

    @staticmethod
    def _reduce_goal(state: dict[str, Any] | None, event: Any) -> dict[str, Any] | None:
        if event.type == "goal/change":
            return dict(event.data)
        return state

    def create_goal(
        self,
        session: Session,
        objective: str,
        max_goal_rounds: int = 20,
        goal_id: str | None = None,
    ) -> GoalView:
        """Create and arm a new goal for `session`."""
        cleaned_obj = objective.strip()
        if not cleaned_obj:
            raise GoalError("create_goal: objective must be a non-empty string")
        if max_goal_rounds < 1:
            raise GoalError("create_goal: max_goal_rounds must be >= 1")

        existing = self._views.get(session.session_id)
        if existing is not None and existing.goal.phase == "active":
            raise GoalError(
                f"create_goal: session already has an active goal ({existing.goal.id}); update or complete it first"
            )

        now = time.time()
        gid = goal_id or f"goal_{uuid.uuid4().hex[:8]}"
        snap = GoalSnapshot(
            id=gid,
            revision=1,
            objective=cleaned_obj,
            phase="active",
            max_goal_rounds=max_goal_rounds,
        )
        view = GoalView(
            goal=snap,
            rounds_started=0,
            created_at=now,
            updated_at=now,
            activation="armed",
        )
        self._views[session.session_id] = view
        session.append("goal/change", view.model_dump())
        return view

    def get_goal(self, session: Session) -> GoalView | None:
        """Return the current GoalView for `session`, or None if no goal exists."""
        return self._views.get(session.session_id)

    def update_goal(
        self,
        session: Session,
        phase: GoalPhase | None = None,
        objective: str | None = None,
        blocked_reason: GoalBlockReason | dict[str, str] | None = None,
        expected_revision: int | None = None,
    ) -> GoalView:
        """Update goal state with CAS revision checking and 3-round blocked floor."""
        view = self._views.get(session.session_id)
        if view is None:
            raise GoalError("update_goal: no goal exists for this session")

        if expected_revision is not None and expected_revision != view.goal.revision:
            raise GoalError(
                f"update_goal: revision mismatch (expected {expected_revision}, actual {view.goal.revision})"
            )

        new_phase = phase or view.goal.phase
        if new_phase == "blocked":
            if view.rounds_started < MIN_ROUNDS_BEFORE_BLOCK:
                raise GoalError(
                    f"update_goal: cannot mark goal as 'blocked' before {MIN_ROUNDS_BEFORE_BLOCK} rounds "
                    f"(only {view.rounds_started} rounds started so far)"
                )
            if blocked_reason is None and view.goal.blocked_reason is None:
                raise GoalError("update_goal: blocked_reason is required when phase='blocked'")

        reason_obj: GoalBlockReason | None = view.goal.blocked_reason
        if isinstance(blocked_reason, dict):
            reason_obj = GoalBlockReason(**blocked_reason)
        elif isinstance(blocked_reason, GoalBlockReason):
            reason_obj = blocked_reason

        new_obj = objective.strip() if objective is not None else view.goal.objective
        if not new_obj:
            raise GoalError("update_goal: objective cannot be empty")

        view.goal.revision += 1
        view.goal.phase = new_phase
        view.goal.objective = new_obj
        view.goal.blocked_reason = reason_obj if new_phase == "blocked" else None
        view.updated_at = time.time()
        if new_phase in ("complete", "paused", "blocked"):
            view.activation = "disarmed"
        else:
            view.activation = "armed"

        session.append("goal/change", view.model_dump())
        return view


class GoalRoundDriver:
    """Race-fenced automatic same-session continuation driver (@deepseek-ai/dsh-goal-round-driver)."""

    def __init__(self, goal_manager: GoalManager):
        self.goal_manager = goal_manager

    def is_drivable(self, session: Session) -> bool:
        """Return True if the session has an active, armed goal within round limits."""
        view = self.goal_manager.get_goal(session)
        if view is None:
            return False
        return (
            view.goal.phase == "active"
            and view.activation == "armed"
            and view.rounds_started < view.goal.max_goal_rounds
        )

    def advance_round(self, session: Session) -> str | None:
        """Increment `rounds_started` and return the next goal continuation prompt if drivable."""
        view = self.goal_manager.get_goal(session)
        if view is None or view.goal.phase != "active" or view.activation != "armed":
            return None

        if view.rounds_started >= view.goal.max_goal_rounds:
            view.goal.phase = "paused"
            view.activation = "disarmed"
            view.updated_at = time.time()
            session.append("goal/change", view.model_dump())
            return None

        view.rounds_started += 1
        view.updated_at = time.time()
        prompt = render_goal_round_prompt(view, view.rounds_started)
        session.append(
            "goal/round",
            {
                "goal_id": view.goal.id,
                "revision": view.goal.revision,
                "round": view.rounds_started,
            },
        )
        return prompt
