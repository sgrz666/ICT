"""Repeat tool call reminder guard (@deepseek-ai/dsh-repeat-tool-reminder).

Tracks consecutive identical tool calls per agent session using deep key-sorted
JSON canonicalization. Emits a gentle reminder at the first threshold (default 3)
and a detailed reminder naming the tool, count, and bounded arguments preview
at subsequent thresholds (default 5, 8).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

GENTLE_REMINDER: str = (
    "You are repeating the exact same tool call with identical arguments. "
    "Carefully analyze the previous result before calling again: if the task is "
    "not complete, try a different approach or different arguments instead of "
    "repeating the call."
)


def detailed_reminder(tool_name: str, count: int, canonical_arguments: str) -> str:
    """Format the detailed later-threshold reminder."""
    return (
        "Repeated tool call detected:\n"
        f"- tool: {tool_name}\n"
        f"- consecutive_calls: {count}\n"
        f"- arguments: {canonical_arguments}\n"
        "The repeated calls are not making progress. Do not call this tool with "
        "these exact arguments again. Inspect the latest result and choose a "
        "different action, different arguments, or finish the task if enough "
        "evidence has been gathered."
    )


def _sort_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_sort_json_value(item) for item in value]
    if isinstance(value, dict):
        return {k: _sort_json_value(value[k]) for k in sorted(value.keys())}
    return value


def canonicalize_arguments(arguments_value: Any) -> str:
    """Canonical string form of a tool call's arguments via deep key sorting."""
    if isinstance(arguments_value, str):
        try:
            parsed = json.loads(arguments_value)
            return json.dumps(_sort_json_value(parsed), ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return arguments_value.strip()
    try:
        return json.dumps(_sort_json_value(arguments_value), ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(arguments_value)


def _wildcard_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.sub(r"[|\\{}()[\]^$+?.]", r"\\\g<0>", pattern)
    return re.compile(f"^{escaped.replace('*', '.*')}$")


@dataclass
class _ChainState:
    last_key: tuple[str, str] | None = None
    count: int = 0


class RepeatToolReminder:
    """Advisory per-session repeat-call detector."""

    def __init__(
        self,
        thresholds: list[int] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        arguments_preview_chars: int = 500,
    ):
        raw_thresholds = thresholds if thresholds is not None else [3, 5, 8]
        if not raw_thresholds:
            raise ValueError("repeat-tool-reminder: thresholds cannot be empty")
        if len(set(raw_thresholds)) != len(raw_thresholds):
            raise ValueError("repeat-tool-reminder: duplicate values in thresholds")
        if any(not isinstance(t, int) or t < 2 for t in raw_thresholds):
            raise ValueError("repeat-tool-reminder: every threshold must be an integer >= 2")

        self.thresholds = sorted(raw_thresholds)
        self.include_patterns = [_wildcard_to_regex(p) for p in (include or [])]
        self.exclude_patterns = [_wildcard_to_regex(p) for p in (exclude or [])]
        self.arguments_preview_chars = max(50, arguments_preview_chars)
        self._states: dict[str, _ChainState] = {}

    def _is_transparent(self, tool_name: str) -> bool:
        if any(rx.match(tool_name) for rx in self.exclude_patterns):
            return True
        if self.include_patterns and not any(rx.match(tool_name) for rx in self.include_patterns):
            return True
        return False

    def record_call(
        self,
        tool_name: str,
        arguments: Any,
        session_id: str = "default",
    ) -> str | None:
        """Record a tool execution and return a reminder string if a threshold is hit."""
        if self._is_transparent(tool_name):
            return None

        canon_args = canonicalize_arguments(arguments)
        call_key = (tool_name, canon_args)

        state = self._states.setdefault(session_id, _ChainState())
        if state.last_key == call_key:
            state.count += 1
        else:
            state.last_key = call_key
            state.count = 1

        if state.count not in self.thresholds:
            return None

        if state.count == self.thresholds[0]:
            return GENTLE_REMINDER

        preview = canon_args
        if len(preview) > self.arguments_preview_chars:
            preview = preview[: self.arguments_preview_chars] + "..."
        return detailed_reminder(tool_name, state.count, preview)

    def get_streak(self, session_id: str = "default") -> int:
        """Return the current consecutive repeat count for `session_id`."""
        state = self._states.get(session_id)
        return state.count if state is not None else 0

    def reset(self, session_id: str | None = None) -> None:
        """Reset repeat tracking state for a session or all sessions."""
        if session_id is None:
            self._states.clear()
        else:
            self._states.pop(session_id, None)
