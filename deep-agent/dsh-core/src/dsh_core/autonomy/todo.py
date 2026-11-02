"""Event-sourced todo list manager (@deepseek-ai/dsh-tool-todo).

Implements whole-list replacement over the Format v4 session log (`todo/write`),
enforcing unique non-empty task descriptions, valid status values
(`pending`, `in_progress`, `completed`), and `allow_parallel_in_progress` constraints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..session.projection import SessionProjectionRegistry
    from ..session.state_machine import Session

TodoStatus = Literal["pending", "in_progress", "completed"]
VALID_TODO_STATUSES = ("pending", "in_progress", "completed")


class TodoItem(BaseModel):
    """Canonical task item in a session todo list."""

    content: str
    status: TodoStatus = "pending"


class TodoValidationError(ValueError):
    """Raised when a todo_write payload violates structural or parallel-progress constraints."""


def validate_todo_list(
    raw_items: list[dict[str, Any] | TodoItem],
    allow_parallel_in_progress: bool = True,
) -> list[TodoItem]:
    """Validate and canonicalize a list of todo items."""
    todos: list[TodoItem] = []
    seen: set[str] = set()
    active_count = 0

    for raw in raw_items:
        if isinstance(raw, TodoItem):
            content = raw.content.strip()
            status = raw.status
        elif isinstance(raw, dict):
            extra_keys = set(raw.keys()) - {"content", "status"}
            if extra_keys:
                raise TodoValidationError(f"invalid todo: unexpected keys {sorted(extra_keys)}")
            content = str(raw.get("content", "")).strip()
            status = str(raw.get("status", ""))  # type: ignore[assignment]
        else:
            raise TodoValidationError(f"invalid todo item type: {type(raw).__name__}")

        if not content:
            raise TodoValidationError("invalid todo: `content` must be a non-empty string")
        if status not in VALID_TODO_STATUSES:
            raise TodoValidationError(
                f"invalid todo status {status!r}: must be one of {VALID_TODO_STATUSES}"
            )
        if content in seen:
            raise TodoValidationError(f'invalid todos: duplicate content "{content}"')

        seen.add(content)
        if status == "in_progress":
            active_count += 1
        todos.append(TodoItem(content=content, status=status))  # type: ignore[arg-type]

    if not allow_parallel_in_progress and active_count > 1:
        raise TodoValidationError(
            f"invalid todos: at most one task may be in_progress (got {active_count})"
        )

    return todos


class TodoManager:
    """Manages session-scoped todo lists and folds `todo/write` events."""

    def __init__(
        self,
        allow_parallel_in_progress: bool = True,
        projection_registry: SessionProjectionRegistry | None = None,
    ):
        self.allow_parallel_in_progress = allow_parallel_in_progress
        if projection_registry is not None:
            projection_registry.register("todos", lambda: None, self._reduce_todos)

    @staticmethod
    def _reduce_todos(state: list[TodoItem] | None, event: Any) -> list[TodoItem] | None:
        if event.type == "todo/write":
            raw_list = event.data.get("todos") or []
            return [TodoItem(**item) if isinstance(item, dict) else item for item in raw_list]
        return state

    def write_todos(
        self,
        session: Session,
        items: list[dict[str, Any] | TodoItem],
    ) -> list[TodoItem]:
        """Validate and append a `todo/write` snapshot to `session`."""
        validated = validate_todo_list(
            items, allow_parallel_in_progress=self.allow_parallel_in_progress
        )
        session.append(
            "todo/write",
            {"todos": [item.model_dump() for item in validated]},
        )
        return validated

    def get_todos(self, session: Session) -> list[TodoItem]:
        """Return the latest todo list from `session.log`."""
        for event in reversed(session.log):
            if event.type == "todo/write":
                raw_list = event.data.get("todos") or []
                return [TodoItem(**item) if isinstance(item, dict) else item for item in raw_list]
        return []
