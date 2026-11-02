"""Token counter and budget meter module.

Provides heuristic token estimation based on character density (4 chars/token),
message formatting overheads, and real provider token usage accumulation.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..session.models import Message

if TYPE_CHECKING:
    from ..session.state_machine import Session


class TokenUsage(BaseModel):
    """Accumulated token usage tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0


class TokenMeter:
    """Estimates and accumulates token usage across conversations."""

    CHARS_PER_TOKEN: float = 4.0
    MESSAGE_OVERHEAD: int = 4
    ROLE_OVERHEAD: int = 2

    def __init__(self):
        self._accumulated = TokenUsage()

    def estimate_text(self, text: str) -> int:
        """Estimate token count for a text string using the 4 chars/token heuristic.

        Returns:
            Estimated integer token count (minimum 0).
        """
        if not text:
            return 0
        return math.ceil(len(text) / self.CHARS_PER_TOKEN)

    def estimate_message(self, message: Message | dict[str, Any]) -> int:
        """Estimate token cost of a single message including structural overhead."""
        if isinstance(message, Message):
            content = message.content or ""
            role = message.role
            tools_cost = 0
            if message.tool_calls:
                for tc in message.tool_calls:
                    tools_cost += self.estimate_text(tc.name) + self.estimate_text(tc.arguments) + 4
        else:
            content = str(message.get("content", ""))
            role = str(message.get("role", "user"))
            tools_cost = 0
            raw_tools = message.get("tool_calls", [])
            for tc in raw_tools:
                tools_cost += self.estimate_text(str(tc)) + 4

        content_tokens = self.estimate_text(content)
        role_tokens = self.estimate_text(role) + self.ROLE_OVERHEAD
        return content_tokens + role_tokens + tools_cost + self.MESSAGE_OVERHEAD

    def estimate_messages(self, messages: list[Message]) -> int:
        """Estimate total tokens across a list of messages."""
        return sum(self.estimate_message(m) for m in messages)

    def estimate_session_surface(self, session: Session) -> int:
        """Estimate total tokens currently visible to the model on the session surface."""
        active_messages = session.derive_messages()
        return self.estimate_messages(active_messages)

    def accumulate_usage(self, usage: TokenUsage | dict[str, Any]) -> None:
        """Record verified token usage reported by an LLM provider."""
        if isinstance(usage, dict):
            inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            out = usage.get("output_tokens", usage.get("completion_tokens", 0))
            cr = usage.get("cache_read_tokens", 0)
            cw = usage.get("cache_write_tokens", 0)
            tot = usage.get("total_tokens", inp + out)
        else:
            inp = usage.input_tokens
            out = usage.output_tokens
            cr = usage.cache_read_tokens
            cw = usage.cache_write_tokens
            tot = usage.total_tokens

        self._accumulated.input_tokens += inp
        self._accumulated.output_tokens += out
        self._accumulated.cache_read_tokens += cr
        self._accumulated.cache_write_tokens += cw
        self._accumulated.total_tokens += tot

    def get_total_usage(self) -> TokenUsage:
        """Return the accumulated token usage statistics."""
        return self._accumulated.model_copy()

    def reset_usage(self) -> None:
        """Reset accumulated provider token usage to zero."""
        self._accumulated = TokenUsage()
