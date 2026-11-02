"""Tool registry and execution pipeline (@deepseek-ai/dsh-tools).

Implements tool registration, OpenAI-compatible JSON Schema export, and the
3-stage `tools/pre-execute -> tools/execute -> tools/post-execute` waterfall
pipeline with timeout guards, spill retention, and repeat-call reminders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    """Normalized request to execute a single tool call."""

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw_tc: dict[str, Any]) -> ToolCallRequest:
        """Parse either OpenAI nested `{"id", "function": {"name", "arguments"}}` or flat dicts."""
        call_id = str(raw_tc.get("id") or raw_tc.get("call_id") or "call_0")
        fn = raw_tc.get("function") if isinstance(raw_tc.get("function"), dict) else {}
        name = str(fn.get("name") or raw_tc.get("name") or "")
        raw_args = fn.get("arguments") if "arguments" in fn else raw_tc.get("arguments", {})

        if isinstance(raw_args, str):
            try:
                args_dict = json.loads(raw_args) if raw_args.strip() else {}
            except Exception:
                args_dict = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            args_dict = dict(raw_args)
        else:
            args_dict = {}

        return cls(call_id=call_id, name=name, arguments=args_dict)


class ToolExecutionResult(BaseModel):
    """Result produced by the tool execution pipeline."""

    call_id: str
    name: str
    content: str
    is_error: bool = False
    spilled: bool = False
    spill_path: str | None = None
    reminder: str | None = None


@dataclass
class ToolDefinition:
    """Declarative specification and handler for a model-facing tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    mutating: bool = False
    parallel_safe: bool = True

    def to_openai_schema(self) -> dict[str, Any]:
        """Export tool definition as an OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


PreExecuteHook = Callable[[str, ToolCallRequest], None]
PostExecuteHook = Callable[[str, ToolCallRequest, ToolExecutionResult], ToolExecutionResult]


class ToolRegistry:
    """Central tool registry and guarded execution pipeline."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._pre_hooks: list[PreExecuteHook] = []
        self._post_hooks: list[PostExecuteHook] = []
        self._timeout_runner: Callable[[str, Callable[..., Any], dict[str, Any]], Any] | None = None

    def register(self, tool_def: ToolDefinition) -> None:
        """Register or replace a tool definition."""
        self._tools[tool_def.name] = tool_def

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_tool(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name!r}")
        return self._tools[name]

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def schemas(self, allowed_names: set[str] | None = None) -> list[dict[str, Any]]:
        """Return OpenAI tool schemas for all (or `allowed_names`) registered tools."""
        result: list[dict[str, Any]] = []
        for name in sorted(self._tools.keys()):
            if allowed_names is not None and name not in allowed_names:
                continue
            result.append(self._tools[name].to_openai_schema())
        return result

    def add_pre_execute_hook(self, hook: PreExecuteHook) -> None:
        """Add a `tools/pre-execute` guard hook `(session_id, call_request) -> None`."""
        self._pre_hooks.append(hook)

    def add_post_execute_hook(self, hook: PostExecuteHook) -> None:
        """Add a `tools/post-execute` transformer `(session_id, call_request, result) -> result`."""
        self._post_hooks.append(hook)

    def set_timeout_runner(
        self, runner: Callable[[str, Callable[..., Any], dict[str, Any]], Any]
    ) -> None:
        """Bind a timeout wrapper `(tool_name, handler, args) -> output`."""
        self._timeout_runner = runner

    def execute_call(
        self,
        call: ToolCallRequest | dict[str, Any],
        session_id: str = "default",
        allowed_names: set[str] | None = None,
    ) -> ToolExecutionResult:
        """Execute a single tool call through the pre -> execute -> post pipeline."""
        req = call if isinstance(call, ToolCallRequest) else ToolCallRequest.from_raw(call)

        if allowed_names is not None and req.name not in allowed_names:
            return ToolExecutionResult(
                call_id=req.call_id,
                name=req.name,
                content=f'Error: Tool "{req.name}" is not available in the active agent preset.',
                is_error=True,
            )

        if req.name not in self._tools:
            return ToolExecutionResult(
                call_id=req.call_id,
                name=req.name,
                content=f'Error: Unknown tool "{req.name}". Available tools: {", ".join(self.list_names())}',
                is_error=True,
            )

        tool_def = self._tools[req.name]

        # 1. tools/pre-execute
        try:
            for pre_hook in self._pre_hooks:
                pre_hook(session_id, req)
        except Exception as exc:
            return ToolExecutionResult(
                call_id=req.call_id,
                name=req.name,
                content=f"Error (pre-execute guard): {type(exc).__name__}: {exc}",
                is_error=True,
            )

        # 2. tools/execute
        is_error = False
        try:
            if self._timeout_runner is not None:
                raw_out = self._timeout_runner(req.name, tool_def.handler, req.arguments)
            else:
                raw_out = tool_def.handler(req.arguments)

            if isinstance(raw_out, str):
                content_str = raw_out
            else:
                content_str = json.dumps(raw_out, ensure_ascii=False, indent=2)
        except Exception as exc:
            is_error = True
            content_str = f"Error executing {req.name}: {type(exc).__name__}: {exc}"

        res = ToolExecutionResult(
            call_id=req.call_id,
            name=req.name,
            content=content_str,
            is_error=is_error,
        )

        # 3. tools/post-execute
        for post_hook in self._post_hooks:
            res = post_hook(session_id, req, res)

        return res
