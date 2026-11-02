"""Windows environment compatibility and shell detection module.

Provides discovery of available Windows shells (PowerShell 7, Windows PowerShell,
Cmd, Git Bash), safe command argument wrapping, and UTF-8 output encoding setup.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def detect_available_shells() -> dict[str, str]:
    """Detect available shells on the host machine.

    Returns:
        Mapping of shell identifier (e.g. 'pwsh', 'powershell', 'cmd', 'bash')
        to absolute executable path.
    """
    shells: dict[str, str] = {}

    # Check pwsh (PowerShell Core / 7+)
    pwsh_path = shutil.which("pwsh")
    if pwsh_path:
        shells["pwsh"] = pwsh_path
    elif sys.platform == "win32":
        well_known_pwsh = Path(r"C:\Program Files\PowerShell\7\pwsh.exe")
        if well_known_pwsh.is_file():
            shells["pwsh"] = str(well_known_pwsh)

    # Check powershell (Windows PowerShell 5.1)
    ps_path = shutil.which("powershell")
    if ps_path:
        shells["powershell"] = ps_path
    elif sys.platform == "win32":
        sys32_ps = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if sys32_ps.is_file():
            shells["powershell"] = str(sys32_ps)

    # Check cmd
    cmd_path = shutil.which("cmd")
    if cmd_path:
        shells["cmd"] = cmd_path
    elif sys.platform == "win32":
        shells["cmd"] = "cmd.exe"

    # Check bash (Git Bash, WSL, or MSYS2)
    bash_path = shutil.which("bash")
    if bash_path:
        shells["bash"] = bash_path
    elif sys.platform == "win32":
        well_known_git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if well_known_git_bash.is_file():
            shells["bash"] = str(well_known_git_bash)

    # On POSIX, ensure sh/bash are mapped
    if sys.platform != "win32":
        sh_path = shutil.which("sh")
        if sh_path:
            shells["sh"] = sh_path

    return shells


def get_default_shell_name() -> str:
    """Return the preferred default shell name for current platform."""
    available = detect_available_shells()
    if sys.platform == "win32":
        if "pwsh" in available:
            return "pwsh"
        if "powershell" in available:
            return "powershell"
        return "cmd"
    else:
        if "bash" in available:
            return "bash"
        if "sh" in available:
            return "sh"
        return "sh"


def build_shell_command(
    cmd: str,
    shell: str | None = None,
) -> tuple[list[str], str]:
    """Wrap command for invocation with the appropriate shell.

    Args:
        cmd: Raw command string to execute.
        shell: Desired shell identifier ('pwsh', 'powershell', 'cmd', 'bash').
            If None, auto-selects preferred shell.

    Returns:
        A tuple of (argv_list, shell_type).
    """
    available = detect_available_shells()
    target_shell = shell or get_default_shell_name()

    if target_shell not in available:
        # Fallback to available shell
        target_shell = get_default_shell_name()

    shell_exe = available[target_shell]

    if target_shell in ("pwsh", "powershell"):
        # UTF-8 preamble ensures output streams correctly encode unicode characters
        utf8_preamble = (
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        )
        c = cmd.strip()
        if (c.startswith('"') or c.startswith("'")) and not c.startswith("&"):
            c = "& " + c
        full_command = utf8_preamble + f"& {{ {c} }}; exit $LASTEXITCODE"
        argv = [
            shell_exe,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            full_command,
        ]
        return argv, target_shell

    elif target_shell == "bash":
        argv = [shell_exe, "-c", cmd]
        return argv, target_shell

    elif target_shell == "cmd":
        argv = [shell_exe, "/d", "/c", cmd]
        return argv, target_shell

    else:
        # Generic fallback
        argv = [shell_exe, "-c", cmd]
        return argv, target_shell
