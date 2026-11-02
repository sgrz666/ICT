"""Tests for the dsh-core sandbox subsystem.

Covers:
- ProcessSandbox execution, exit codes, stdout/stderr capture, timeout handling
- Windows process tree termination and shell command building
- SandboxPolicy enforcement (READ_ONLY, WORKSPACE_WRITE, DANGER_FULL_ACCESS)
- PolicyChecker path containment and mutating command blocking
- MockSandboxProvider exact, regex, and dynamic handlers
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from dsh_core.sandbox import (
    CommandResult,
    MockSandboxProvider,
    PolicyChecker,
    PolicyViolationError,
    ProcessSandbox,
    SandboxPolicy,
    build_shell_command,
    detect_available_shells,
)


# ==============================================================================
# Tier 1: ProcessSandbox Subprocess Execution
# ==============================================================================


def test_process_sandbox_simple_success(temp_workspace: Path):
    """Test successful command execution capturing stdout and exit code 0."""
    sandbox = ProcessSandbox(workspace_root=temp_workspace)
    cmd = f'{sys.executable} -c "print(\'hello_from_sandbox\')"'
    res = sandbox.execute(cmd)

    assert res.is_success
    assert res.exit_code == 0
    assert not res.timed_out
    assert "hello_from_sandbox" in res.stdout
    assert res.duration_ms > 0


def test_process_sandbox_stderr_and_nonzero_exit(temp_workspace: Path):
    """Test command failure capturing stderr and non-zero exit code."""
    sandbox = ProcessSandbox(workspace_root=temp_workspace)
    cmd = f'{sys.executable} -c "import sys; sys.stderr.write(\'fatal_err\'); sys.exit(42)"'
    res = sandbox.execute(cmd)

    assert not res.is_success
    assert res.exit_code == 42
    assert "fatal_err" in res.stderr


def test_process_sandbox_timeout_handling(temp_workspace: Path):
    """Test that long-running commands time out and are terminated."""
    sandbox = ProcessSandbox(workspace_root=temp_workspace, default_timeout=0.4)
    cmd = f'{sys.executable} -c "import time; time.sleep(5)"'
    start_t = time.time()
    res = sandbox.execute(cmd, timeout=0.3)
    elapsed = time.time() - start_t

    assert res.timed_out
    assert res.exit_code != 0
    assert elapsed < 4.5  # Terminated early, did not sleep full 5s


def test_process_sandbox_working_directory(temp_workspace: Path):
    """Test that command executes in the specified contained working directory."""
    sandbox = ProcessSandbox(workspace_root=temp_workspace)
    sub = temp_workspace / "src_sub"
    cmd = f'{sys.executable} -c "import os; print(os.getcwd())"'
    res = sandbox.execute(cmd, cwd=sub)

    assert res.is_success
    assert str(sub.resolve()).lower() in res.stdout.strip().lower()


def test_process_sandbox_custom_env(temp_workspace: Path):
    """Test passing custom environment variables."""
    sandbox = ProcessSandbox(workspace_root=temp_workspace)
    cmd = f'{sys.executable} -c "import os; print(os.environ.get(\'DSH_TEST_VAR\', \'\'))"'
    res = sandbox.execute(cmd, env={"DSH_TEST_VAR": "custom_val_123"})

    assert res.is_success
    assert "custom_val_123" in res.stdout


# ==============================================================================
# Tier 2: Shell Compatibility & Helpers
# ==============================================================================


def test_detect_available_shells():
    """Test discovering available shells on the host machine."""
    shells = detect_available_shells()
    assert isinstance(shells, dict)
    if sys.platform == "win32":
        # Windows typically has cmd or powershell
        assert "cmd" in shells or "powershell" in shells
    else:
        assert "sh" in shells or "bash" in shells


def test_build_shell_command():
    """Test constructing wrapped shell execution commands."""
    cmd_str = "echo 123"
    argv, shell_type = build_shell_command(cmd_str)
    assert isinstance(argv, list)
    assert any("echo" in arg or "123" in arg for arg in argv)


# ==============================================================================
# Tier 3: Policy Enforcement (PolicyChecker)
# ==============================================================================


def test_policy_read_only_blocks_mutating_commands(temp_workspace: Path):
    """READ_ONLY policy must block file deletions and writes."""
    checker = PolicyChecker(SandboxPolicy.READ_ONLY, temp_workspace)

    # Benign read commands
    checker.validate_command("python test.py")
    checker.validate_command("ls -la")

    # Mutating commands
    with pytest.raises(PolicyViolationError, match="potentially mutating token"):
        checker.validate_command("rm -rf ./temp")

    with pytest.raises(PolicyViolationError):
        checker.validate_command("echo data > output.txt")

    with pytest.raises(PolicyViolationError):
        checker.validate_command("del /F important.txt")


def test_policy_workspace_write_containment(temp_workspace: Path):
    """WORKSPACE_WRITE permits writes within workspace but blocks cwd escaping."""
    checker = PolicyChecker(SandboxPolicy.WORKSPACE_WRITE, temp_workspace)

    # Valid cwd inside workspace
    valid_cwd = checker.validate_working_directory("src_sub")
    assert valid_cwd == (temp_workspace / "src_sub").resolve()

    # Escaped cwd
    with pytest.raises(PolicyViolationError, match="escapes workspace root"):
        checker.validate_working_directory(temp_workspace / "..")

    # Critical forbidden patterns
    with pytest.raises(PolicyViolationError, match="Critical command token forbidden"):
        checker.validate_command("format C: /y")


def test_policy_danger_full_access(temp_workspace: Path):
    """DANGER_FULL_ACCESS bypasses containment and mutating filters."""
    checker = PolicyChecker(SandboxPolicy.DANGER_FULL_ACCESS, temp_workspace)

    # Does not raise even on external directory or dangerous tokens
    ext_dir = Path("C:/") if sys.platform == "win32" else Path("/tmp")
    assert checker.validate_working_directory(ext_dir) == ext_dir.resolve()
    checker.validate_command("rm -rf /")


# ==============================================================================
# Tier 4: MockSandboxProvider
# ==============================================================================


def test_mock_sandbox_provider(temp_workspace: Path):
    """Test MockSandboxProvider pattern matching and dynamic handlers."""
    mock_sb = MockSandboxProvider(workspace_root=temp_workspace)

    # Exact match
    mock_sb.register_mock(
        "git status",
        CommandResult(exit_code=0, stdout="On branch main\nnothing to commit"),
    )

    # Regex match
    mock_sb.register_mock(
        r"^pytest.*",
        CommandResult(exit_code=0, stdout="25 passed in 0.42s"),
        is_regex=True,
    )

    # Dynamic handler
    mock_sb.register_handler(
        predicate=lambda c: "special" in c,
        handler=lambda c: CommandResult(exit_code=0, stdout=f"handled:{c}"),
    )

    # Execute exact
    res1 = mock_sb.execute("git status")
    assert res1.stdout == "On branch main\nnothing to commit"

    # Execute regex
    res2 = mock_sb.execute("pytest tests/unit")
    assert "25 passed" in res2.stdout

    # Execute handler
    res3 = mock_sb.execute("run special job")
    assert res3.stdout == "handled:run special job"

    # Default fallback for unmocked command
    res4 = mock_sb.execute("unknown command")
    assert res4.is_success
    assert "mock simulated" in res4.stdout.lower()

    # Verify execution tracking
    assert len(mock_sb.executed_commands) == 4
    assert mock_sb.executed_commands[0]["command"] == "git status"

    # Clear
    mock_sb.clear_mocks()
    assert len(mock_sb.executed_commands) == 0
