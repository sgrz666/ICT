"""Plan mode enforcement and exit approval (@deepseek-ai/dsh-plan-mode).

Restricts the agent to read-only exploration while plan mode is active, provides
the official plan-mode system prompt guidance, and manages plan submission and
review via `exit_plan_mode`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..session.state_machine import Session

PLAN_MODE_SECTION: str = (
    "You are in plan mode. Stay in plan mode until the user approves your plan through "
    "exit_plan_mode or switches the session mode. Imperative language to implement changes "
    "means plan the implementation, not execute it.\n\n"
    "Explore first. Use non-mutating reads, searches, static analysis, and checks to ground "
    "the plan in the actual repository. Do not edit or write files, change configuration, or "
    "otherwise carry out the plan.\n\n"
    "Make the plan decision-complete: state the goal and success criteria; group implementation "
    "changes by subsystem; identify public API, schema, and data-flow changes; cover edge cases, "
    "failure modes, tests, acceptance criteria, and explicit assumptions.\n\n"
    "When ready, call exit_plan_mode with the complete plan markdown, starting with a # title."
)


class PlanModeViolationError(PermissionError):
    """Raised when a mutating tool is invoked while the session is in plan mode."""


class PlanSubmissionResult(BaseModel):
    """Result of submitting a plan via `exit_plan_mode`."""

    approved: bool
    plan_markdown: str
    feedback: str = ""
    exited_plan_mode: bool = False


class PlanModeManager:
    """Manages per-session plan mode state, tool mutation guards, and plan approval."""

    MUTATING_TOOLS: set[str] = {
        "write",
        "write_file",
        "edit",
        "edit_file",
        "str_replace_editor",
        "delete_file",
        "todo_write",
    }

    def __init__(
        self,
        approval_callback: Callable[[str], tuple[bool, str]] | None = None,
    ):
        self.approval_callback = approval_callback
        self._active_sessions: set[str] = set()
        self._approved_plans: dict[str, str] = {}

    def enter_plan_mode(self, session: Session) -> None:
        """Activate plan mode for `session` and log a `plan/enter` event."""
        self._active_sessions.add(session.session_id)
        session.append("plan/enter", {"active": True})

    def is_active(self, session_id: str) -> bool:
        """Return True if `session_id` is currently in plan mode."""
        return session_id in self._active_sessions

    def get_system_prompt_section(self, session_id: str) -> str | None:
        """Return the plan-mode prompt section if plan mode is active for `session_id`."""
        return PLAN_MODE_SECTION if self.is_active(session_id) else None

    def check_tool_allowed(self, session_id: str, tool_name: str) -> None:
        """Raise `PlanModeViolationError` if `tool_name` is mutating and plan mode is active."""
        if self.is_active(session_id) and tool_name in self.MUTATING_TOOLS:
            raise PlanModeViolationError(
                f'Tool "{tool_name}" is forbidden while in plan mode. '
                "Use read-only inspection tools and submit your plan via exit_plan_mode first."
            )

    def exit_plan_mode(
        self,
        session: Session,
        plan_markdown: str,
    ) -> PlanSubmissionResult:
        """Submit `plan_markdown` for approval and exit plan mode if approved."""
        cleaned = plan_markdown.strip()
        if not cleaned.startswith("#"):
            raise ValueError("exit_plan_mode: plan_markdown must start with a Markdown `#` heading")

        if self.approval_callback is not None:
            approved, feedback = self.approval_callback(cleaned)
        else:
            approved, feedback = True, "Plan approved automatically."

        if approved:
            self._active_sessions.discard(session.session_id)
            self._approved_plans[session.session_id] = cleaned
            session.append(
                "plan/exit",
                {"approved": True, "plan": cleaned, "feedback": feedback},
            )
            return PlanSubmissionResult(
                approved=True,
                plan_markdown=cleaned,
                feedback=feedback,
                exited_plan_mode=True,
            )

        session.append(
            "plan/rejected",
            {"approved": False, "plan": cleaned, "feedback": feedback},
        )
        return PlanSubmissionResult(
            approved=False,
            plan_markdown=cleaned,
            feedback=feedback,
            exited_plan_mode=False,
        )

    def get_approved_plan(self, session_id: str) -> str | None:
        """Return the last approved plan markdown for `session_id`, if any."""
        return self._approved_plans.get(session_id)
