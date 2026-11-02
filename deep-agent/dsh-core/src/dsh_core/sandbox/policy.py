"""Sandbox permission policy module.

Defines the security execution policies (read-only, workspace-write, danger-full-access)
and policy checkers that inspect command strings and working directories before execution.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from ..file.containment import FsSandboxDeniedError, is_path_contained


class SandboxPolicy(str, Enum):
    """Sandbox execution policy levels."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class PolicyViolationError(FsSandboxDeniedError):
    """Raised when an operation violates the active sandbox policy."""


class PolicyChecker:
    """Evaluates commands and file paths against the active sandbox policy."""

    # Commands that typically alter state or delete files
    DANGEROUS_WRITE_PATTERNS = [
        r"\b(rm|del|erase|rmdir|rd)\b",
        r"\b(format|diskpart|mkfs)\b",
        r"\b(git\s+(commit|push|rebase|merge|reset\s+--hard))\b",
        r"(>|>>)",  # Redirection writes
        r"\b(chmod|chown|attrib)\b",
        r"\b(kill|pkill|taskkill)\b",
        r"\b(reg|regedit)\b",
    ]

    def __init__(self, policy: SandboxPolicy, workspace_root: str | Path):
        self.policy = policy
        self.workspace_root = Path(workspace_root).resolve()
        self._write_regex = re.compile("|".join(self.DANGEROUS_WRITE_PATTERNS), re.IGNORECASE)

    def validate_working_directory(self, cwd: str | Path | None) -> Path:
        """Validate that the execution working directory complies with the policy.

        Returns:
            The resolved valid Path.

        Raises:
            PolicyViolationError: If cwd violates the policy.
        """
        if cwd is None:
            return self.workspace_root

        target_dir = Path(cwd)
        if not target_dir.is_absolute():
            target_dir = self.workspace_root / target_dir

        if self.policy == SandboxPolicy.DANGER_FULL_ACCESS:
            return target_dir.resolve()

        if not is_path_contained(target_dir, self.workspace_root):
            raise PolicyViolationError(
                f"Working directory '{cwd}' escapes workspace root '{self.workspace_root}' "
                f"under policy '{self.policy.value}'."
            )

        return target_dir.resolve()

    def validate_command(self, cmd: str) -> None:
        """Validate that a command string does not violate policy constraints.

        Raises:
            PolicyViolationError: If command is not allowed under current policy.
        """
        if self.policy == SandboxPolicy.DANGER_FULL_ACCESS:
            return

        if self.policy == SandboxPolicy.READ_ONLY:
            match = self._write_regex.search(cmd)
            if match:
                raise PolicyViolationError(
                    f"Command '{cmd}' contains potentially mutating token '{match.group()}', "
                    f"which is forbidden under '{SandboxPolicy.READ_ONLY.value}' policy."
                )

        if self.policy == SandboxPolicy.WORKSPACE_WRITE:
            # Under WORKSPACE_WRITE, system formatting or registry tampering is still blocked
            critical_patterns = [r"\b(format|diskpart|mkfs|regedit)\b"]
            for cp in critical_patterns:
                if re.search(cp, cmd, re.IGNORECASE):
                    raise PolicyViolationError(
                        f"Critical command token forbidden under '{SandboxPolicy.WORKSPACE_WRITE.value}': {cmd}"
                    )
