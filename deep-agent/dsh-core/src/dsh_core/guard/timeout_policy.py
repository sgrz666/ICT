"""Tool call timeout policy (@deepseek-ai/dsh-tool-call-timeout-policy).

Enforces per-tool execution deadlines and provides structured timeout handling.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Callable


class ToolCallTimeoutError(TimeoutError):
    """Raised when a tool execution exceeds its configured deadline."""

    def __init__(self, tool_name: str, timeout_seconds: float):
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        super().__init__(f'Tool "{tool_name}" timed out after {timeout_seconds:.2f}s (TOOL_TIMEOUT)')


class ToolTimeoutPolicy:
    """Wraps tool invocations with configurable per-tool deadlines."""

    def __init__(
        self,
        default_timeout_seconds: float = 60.0,
        per_tool_timeouts: dict[str, float] | None = None,
    ):
        self.default_timeout_seconds = max(0.1, default_timeout_seconds)
        self.per_tool_timeouts: dict[str, float] = dict(per_tool_timeouts or {})

    def set_tool_timeout(self, tool_name: str, timeout_seconds: float) -> None:
        """Configure a custom timeout deadline for a specific tool."""
        self.per_tool_timeouts[tool_name] = max(0.05, timeout_seconds)

    def get_timeout(self, tool_name: str) -> float:
        """Resolve the effective timeout in seconds for `tool_name`."""
        return self.per_tool_timeouts.get(tool_name, self.default_timeout_seconds)

    def execute_with_timeout(
        self,
        tool_name: str,
        fn: Callable[..., Any],
        *args: Any,
        timeout_override: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run `fn(*args, **kwargs)` with a deadline, raising `ToolCallTimeoutError` on expiration."""
        deadline = timeout_override if timeout_override is not None else self.get_timeout(tool_name)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=deadline)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ToolCallTimeoutError(tool_name, deadline) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
