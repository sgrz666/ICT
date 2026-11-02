"""User approval and permission presets (@deepseek-ai/dsh-user-approval & @deepseek-ai/dsh-permission-presets).

Defines the three shipped permission presets (`read-only`, `workspace-write`,
`danger-full-access`) and the approval gate invoked before sensitive tool executions.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel

from ..sandbox.policy import SandboxPolicy

ApprovalPolicy = Literal["ask", "never"]
PresetName = Literal["read-only", "workspace-write", "danger-full-access"]


class ApprovalDeniedError(PermissionError):
    """Raised when a user or policy denies approval for a tool invocation."""


class PermissionPreset(BaseModel):
    """Combined sandbox and approval configuration for a permission preset."""

    name: PresetName
    sandbox: SandboxPolicy
    approval: ApprovalPolicy


DEFAULT_PERMISSION_PRESETS: dict[PresetName, PermissionPreset] = {
    "read-only": PermissionPreset(
        name="read-only",
        sandbox=SandboxPolicy.READ_ONLY,
        approval="ask",
    ),
    "workspace-write": PermissionPreset(
        name="workspace-write",
        sandbox=SandboxPolicy.WORKSPACE_WRITE,
        approval="ask",
    ),
    "danger-full-access": PermissionPreset(
        name="danger-full-access",
        sandbox=SandboxPolicy.DANGER_FULL_ACCESS,
        approval="never",
    ),
}


class ApprovalManager:
    """Evaluates and dispatches one-shot user approval checks for tool calls."""

    # Tools that require approval when policy == 'ask' and preset is read-only or sensitive
    SENSITIVE_TOOLS: set[str] = {
        "run_command",
        "pwsh",
        "bash",
        "delete_file",
    }

    WRITE_TOOLS: set[str] = {
        "write",
        "write_file",
        "edit",
        "edit_file",
        "str_replace_editor",
    }

    def __init__(
        self,
        preset: PresetName = "workspace-write",
        approval_handler: Callable[[str, dict[str, Any]], tuple[bool, str]] | None = None,
    ):
        if preset not in DEFAULT_PERMISSION_PRESETS:
            raise ValueError(f"Unknown permission preset: {preset!r}")
        self.current_preset: PermissionPreset = DEFAULT_PERMISSION_PRESETS[preset]
        self.approval_handler = approval_handler

    def set_preset(self, preset: PresetName) -> PermissionPreset:
        """Switch active permission preset."""
        if preset not in DEFAULT_PERMISSION_PRESETS:
            raise ValueError(f"Unknown permission preset: {preset!r}")
        self.current_preset = DEFAULT_PERMISSION_PRESETS[preset]
        return self.current_preset

    def requires_approval(self, tool_name: str) -> bool:
        """Return True if `tool_name` requires user approval under the current preset."""
        if self.current_preset.approval == "never":
            return False
        if self.current_preset.sandbox == SandboxPolicy.READ_ONLY:
            return tool_name in self.SENSITIVE_TOOLS or tool_name in self.WRITE_TOOLS
        return tool_name in self.SENSITIVE_TOOLS

    def check_approval(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Request approval if required; raise `ApprovalDeniedError` if rejected."""
        if not self.requires_approval(tool_name):
            return

        if self.approval_handler is None:
            # If no interactive handler is bound in workspace-write mode, allow standard workspace commands
            # unless in read-only mode where mutations are strictly blocked without explicit approval
            if self.current_preset.sandbox == SandboxPolicy.READ_ONLY:
                raise ApprovalDeniedError(
                    f'Tool "{tool_name}" requires approval in read-only preset, and no approval channel is bound'
                )
            return

        approved, reason = self.approval_handler(tool_name, arguments)
        if not approved:
            raise ApprovalDeniedError(
                f'User denied approval for tool "{tool_name}": {reason or "Rejected by user"}'
            )
