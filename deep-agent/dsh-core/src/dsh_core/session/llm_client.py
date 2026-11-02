"""Pluggable LLM client abstraction and implementations.

Provides the BaseLlmClient protocol, an in-memory deterministic MockLlmClient
for offline unit testing, and an OpenAI/DeepSeek-compatible API client.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, AsyncIterator, Callable, Protocol

from .models import Message, ToolCall


class BaseLlmClient(Protocol):
    """Protocol for language model client providers."""

    async def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> Message:
        """Generate a complete assistant response given conversational messages."""
        ...

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated text chunks from the model."""
        ...


class MockLlmClient:
    """Deterministic, offline mock client for tests and demonstrations."""

    def __init__(
        self,
        canned_responses: list[Message | str] | None = None,
        response_generator: Callable[[list[Message]], Message | str] | None = None,
    ):
        self._responses: list[Message | str] = list(canned_responses) if canned_responses else []
        self._generator = response_generator
        self.call_history: list[list[Message]] = []

    def queue_response(self, response: Message | str) -> None:
        """Queue a canned response to be returned by the next generate() call."""
        self._responses.append(response)

    async def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> Message:
        """Return next canned response or dynamically generated response."""
        self.call_history.append(list(messages))

        if self._generator is not None:
            gen_res = self._generator(messages)
            if isinstance(gen_res, str):
                return Message(role="assistant", content=gen_res)
            return gen_res

        if self._responses:
            next_res = self._responses.pop(0)
            if isinstance(next_res, str):
                return Message(role="assistant", content=next_res)
            return next_res

        # Default fallback
        last_msg = messages[-1].content if messages else ""
        return Message(
            role="assistant",
            content=f"[MockLLM answer to: {last_msg[:40]}]",
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the generated message content word by word."""
        msg = await self.generate(messages, tools=tools)
        words = msg.content.split()
        for word in words:
            yield word + " "


class OpenAiCompatibleClient:
    """Client for OpenAI / DeepSeek / Ollama / vLLM compatible Chat Completions API."""

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com",
        api_key: str = "dummy-key",
        model: str = "deepseek-chat",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> Message:
        """Send chat completion request to the API."""
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result_json = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return Message(
                role="assistant",
                content=f"[API Connection Error: {e}]",
            )

        choices = result_json.get("choices", [])
        if not choices:
            return Message(role="assistant", content="")

        choice_msg = choices[0].get("message", {})
        raw_tools = choice_msg.get("tool_calls", [])
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", "{}"),
            )
            for tc in raw_tools
        ] if raw_tools else None

        return Message(
            role="assistant",
            content=choice_msg.get("content") or "",
            tool_calls=tool_calls,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chunks from completion."""
        # Standard non-stream fallback if stream not implemented
        msg = await self.generate(messages, tools=tools)
        yield msg.content
