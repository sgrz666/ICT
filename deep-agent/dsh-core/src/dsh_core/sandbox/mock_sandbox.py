"""In-process mock sandbox for offline testing and deterministic CI runs.

Provides simulated command execution without spawning real OS child processes,
ideal for test suites, constrained environments, or reproducible educational examples.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

from .policy import PolicyChecker, SandboxPolicy
from .process_runner import CommandResult


class MockSandboxProvider:
    """Mock sandbox executor implementing the ProcessSandbox execution interface."""

    def __init__(
        self,
        workspace_root: str | Path,
        default_policy: SandboxPolicy = SandboxPolicy.WORKSPACE_WRITE,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.default_policy = default_policy
        self._exact_mocks: dict[str, CommandResult] = {}
        self._regex_mocks: list[tuple[re.Pattern, CommandResult]] = []
        self._handlers: list[tuple[Callable[[str], bool], Callable[[str], CommandResult]]] = []
        self.executed_commands: list[dict[str, str | float | bool]] = []

    def register_mock(
        self,
        pattern: str,
        result: CommandResult,
        is_regex: bool = False,
    ) -> None:
        """Register a canned CommandResult for a command string or regex pattern."""
        if is_regex:
            self._regex_mocks.append((re.compile(pattern), result))
        else:
            self._exact_mocks[pattern.strip()] = result

    def register_handler(
        self,
        predicate: Callable[[str], bool],
        handler: Callable[[str], CommandResult],
    ) -> None:
        """Register a dynamic handler function for matching commands."""
        self._handlers.append((predicate, handler))

    def clear_mocks(self) -> None:
        """Clear all registered mocks and handlers."""
        self._exact_mocks.clear()
        self._regex_mocks.clear()
        self._handlers.clear()
        self.executed_commands.clear()

    def execute(
        self,
        cmd: str,
        cwd: str | Path | None = None,
        policy: SandboxPolicy | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        shell: str | None = None,
    ) -> CommandResult:
        """Simulate command execution adhering to sandbox policies.

        Returns:
            Preprogrammed or simulated CommandResult.
        """
        active_policy = policy or self.default_policy
        checker = PolicyChecker(active_policy, self.workspace_root)
        valid_cwd = checker.validate_working_directory(cwd)
        checker.validate_command(cmd)

        clean_cmd = cmd.strip()
        start = time.perf_counter()

        # Check exact mocks
        if clean_cmd in self._exact_mocks:
            res = self._exact_mocks[clean_cmd]
            self._record(clean_cmd, str(valid_cwd), res)
            return res

        # Check regex mocks
        for regex, res in self._regex_mocks:
            if regex.search(clean_cmd):
                self._record(clean_cmd, str(valid_cwd), res)
                return res

        # Check dynamic handlers
        for predicate, handler in self._handlers:
            if predicate(clean_cmd):
                res = handler(clean_cmd)
                self._record(clean_cmd, str(valid_cwd), res)
                return res

        # Fallback simulation for standard built-ins
        simulated = self._simulate_builtin(clean_cmd, valid_cwd)
        duration_ms = (time.perf_counter() - start) * 1000.0
        simulated.duration_ms = round(duration_ms, 2)
        self._record(clean_cmd, str(valid_cwd), simulated)
        return simulated

    def _simulate_builtin(self, cmd: str, cwd: Path) -> CommandResult:
        """Simulate standard shell builtins like echo, pwd, dir, ls."""
        parts = cmd.split()
        if not parts:
            return CommandResult(exit_code=0, stdout="")

        cmd_name = parts[0].lower()

        if cmd_name == "echo":
            # Echo remainder of command
            content = cmd[4:].strip()
            # Strip surrounding quotes if present
            if (content.startswith('"') and content.endswith('"')) or (
                content.startswith("'") and content.endswith("'")
            ):
                content = content[1:-1]
            return CommandResult(exit_code=0, stdout=content + "\n")

        elif cmd_name in ("pwd", "cd"):
            return CommandResult(exit_code=0, stdout=str(cwd) + "\n")

        elif cmd_name in ("ls", "dir"):
            try:
                items = [p.name for p in cwd.iterdir()]
                return CommandResult(exit_code=0, stdout="\n".join(items) + "\n")
            except Exception as e:
                return CommandResult(exit_code=1, stderr=str(e))

        # Default fallback for unmocked command
        return CommandResult(
            exit_code=0,
            stdout=f"[mock simulated execution of: {cmd}]\n",
            stderr="",
        )

    def _record(self, cmd: str, cwd: str, result: CommandResult) -> None:
        self.executed_commands.append({
            "command": cmd,
            "cwd": cwd,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        })
