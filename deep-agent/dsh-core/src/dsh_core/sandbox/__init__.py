"""Sandbox subsystem for dsh-core.

Provides process execution with timeout and process-tree termination on Windows,
permission policies (read-only, workspace-write, danger-full-access), shell detection,
and an in-process mock sandbox for offline testing.
"""

from .jobs import BackgroundJobManager, JobOutputSnapshot, JobStatus, JobSummary
from .mock_sandbox import MockSandboxProvider
from .policy import PolicyChecker, PolicyViolationError, SandboxPolicy
from .process_runner import CommandResult, ProcessSandbox
from .windows_compat import build_shell_command, detect_available_shells

__all__ = [
    "ProcessSandbox",
    "BackgroundJobManager",
    "JobStatus",
    "JobSummary",
    "JobOutputSnapshot",
    "MockSandboxProvider",
    "SandboxPolicy",
    "PolicyChecker",
    "PolicyViolationError",
    "CommandResult",
    "detect_available_shells",
    "build_shell_command",
]
