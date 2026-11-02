"""Process runner with Windows process tree termination and sandbox policy enforcement.

Executes commands in controlled subprocesses with timeout management, exit code
capture, and taskkill /F /T recursive cleanup on Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .policy import PolicyChecker, SandboxPolicy
from .windows_compat import build_shell_command


class CommandResult(BaseModel):
    """Execution result of a sandboxed command."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        """Return True if command finished with exit code 0 and did not time out."""
        return self.exit_code == 0 and not self.timed_out


class ProcessSandbox:
    """Controlled subprocess sandbox runner."""

    def __init__(
        self,
        workspace_root: str | Path,
        default_policy: SandboxPolicy = SandboxPolicy.WORKSPACE_WRITE,
        default_timeout: float = 30.0,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.default_policy = default_policy
        self.default_timeout = default_timeout

    def kill_process_tree(self, pid: int) -> None:
        """Recursively terminate a process tree."""
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            except Exception:
                pass
        else:
            try:
                # Send SIGKILL to process
                os.kill(pid, 9)
            except (OSError, ProcessLookupError):
                pass

    def execute(
        self,
        cmd: str,
        cwd: str | Path | None = None,
        policy: SandboxPolicy | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        shell: str | None = None,
    ) -> CommandResult:
        """Execute a command under policy restrictions with timeout management.

        Args:
            cmd: Command string to execute.
            cwd: Working directory. If relative, resolved against workspace_root.
            policy: Execution policy override (default: instance default_policy).
            timeout: Timeout in seconds (default: instance default_timeout).
            env: Custom environment variables dict.
            shell: Explicit shell choice ('pwsh', 'powershell', 'cmd', 'bash').

        Returns:
            CommandResult with exit code, stdout, stderr, and timing.

        Raises:
            PolicyViolationError: If cwd or command violates policy.
        """
        active_policy = policy or self.default_policy
        effective_timeout = timeout if timeout is not None else self.default_timeout

        checker = PolicyChecker(active_policy, self.workspace_root)
        valid_cwd = checker.validate_working_directory(cwd)
        checker.validate_command(cmd)

        argv, shell_used = build_shell_command(cmd, shell=shell)

        # Scrub and prepare environment
        merged_env = os.environ.copy()
        # Force UTF-8 environment settings for Python & Node subprocesses
        merged_env["PYTHONIOENCODING"] = "utf-8"
        merged_env["PYTHONUTF8"] = "1"
        if env:
            merged_env.update(env)

        start_time = time.perf_counter()
        proc = None
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        exit_code = -1

        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(valid_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=merged_env,
            )

            stdout_text, stderr_text = proc.communicate(timeout=effective_timeout)
            exit_code = proc.returncode

        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            if proc and proc.pid:
                self.kill_process_tree(proc.pid)
                try:
                    # Drain remaining output after kill
                    rem_stdout, rem_stderr = proc.communicate(timeout=2)
                    stdout_text = (stdout_text or "") + (rem_stdout or "")
                    stderr_text = (stderr_text or "") + (rem_stderr or "")
                except Exception:
                    pass
            stderr_text += f"\n[Process timed out after {effective_timeout}s and was terminated.]"

        except Exception as exc:
            exit_code = 1
            stderr_text += f"\n[Execution error: {exc}]"

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return CommandResult(
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            timed_out=timed_out,
            duration_ms=round(duration_ms, 2),
        )
