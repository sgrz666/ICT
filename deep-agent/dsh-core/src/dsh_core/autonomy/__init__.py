"""Autonomy, planning, and goal subsystem for dsh-core.

Implements event-sourced todo lists (`@deepseek-ai/dsh-tool-todo`), read-only
plan mode with approval gates (`@deepseek-ai/dsh-plan-mode`), and same-session
persistent goals with a 3-round blocked floor (`@deepseek-ai/dsh-goal` &
`@deepseek-ai/dsh-goal-round-driver`).
"""

from .goal import (
    MIN_ROUNDS_BEFORE_BLOCK,
    GoalActivation,
    GoalBlockReason,
    GoalError,
    GoalManager,
    GoalPhase,
    GoalRoundDriver,
    GoalSnapshot,
    GoalView,
    render_goal_round_prompt,
)
from .plan_mode import (
    PLAN_MODE_SECTION,
    PlanModeManager,
    PlanModeViolationError,
    PlanSubmissionResult,
)
from .todo import TodoItem, TodoManager, TodoStatus, TodoValidationError, validate_todo_list

__all__ = [
    "TodoItem",
    "TodoStatus",
    "TodoManager",
    "TodoValidationError",
    "validate_todo_list",
    "PLAN_MODE_SECTION",
    "PlanModeManager",
    "PlanModeViolationError",
    "PlanSubmissionResult",
    "MIN_ROUNDS_BEFORE_BLOCK",
    "GoalPhase",
    "GoalActivation",
    "GoalBlockReason",
    "GoalSnapshot",
    "GoalView",
    "GoalError",
    "GoalManager",
    "GoalRoundDriver",
    "render_goal_round_prompt",
]
