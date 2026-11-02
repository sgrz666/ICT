"""Zero-elevation path containment security module.

Verifies that all target file and directory paths remain strictly within the
canonical boundary of the configured workspace root, preventing directory
traversal attacks (e.g., '../', drive letter hops, or symlink escapes) without
requiring OS administrator or elevated token privileges.
"""

from __future__ import annotations

import os
from pathlib import Path


class FsError(Exception):
    """Base exception for all dsh-core filesystem operations."""


class FsNotFoundError(FsError, FileNotFoundError):
    """Raised when a requested file or directory does not exist."""


class FsSandboxDeniedError(FsError, PermissionError):
    """Raised when an operation attempts to access paths outside the workspace boundary."""


class FsAmbiguousEditError(FsError, ValueError):
    """Raised when an edit string matches multiple locations ambiguously."""


class FsEditNotFoundError(FsError, ValueError):
    """Raised when the target string to replace is not found in content."""


def _canonicalize_path(path: str | Path) -> Path:
    """Resolve a path to its canonical representation, even if it does not yet exist.

    If the full path exists, Path.resolve() is used directly.
    If it does not exist, the deepest existing parent directory is resolved,
    and remaining tail components are joined.
    """
    p = Path(path).expanduser()
    if p.exists():
        return p.resolve()

    # Find the deepest existing parent
    parts = p.parts
    # Traverse backwards until an existing ancestor is found
    for i in range(len(parts) - 1, 0, -1):
        ancestor = Path(*parts[:i])
        if ancestor.exists():
            resolved_ancestor = ancestor.resolve()
            remainder = Path(*parts[i:])
            return (resolved_ancestor / remainder).resolve()

    return Path(os.path.abspath(str(p)))


def assert_path_contained(target_path: str | Path, workspace_root: str | Path) -> Path:
    """Assert that target_path is strictly within workspace_root.

    Args:
        target_path: Relative or absolute path to check.
        workspace_root: Canonical workspace root directory.

    Returns:
        The canonical resolved Path of target_path.

    Raises:
        FsSandboxDeniedError: If target_path resolves outside workspace_root.
    """
    canonical_root = _canonicalize_path(workspace_root)
    canonical_target = _canonicalize_path(target_path)

    # Check containment
    try:
        if canonical_target == canonical_root:
            return canonical_target
        if canonical_target.is_relative_to(canonical_root):
            return canonical_target
    except AttributeError:
        # Fallback for older python or complex relative path checks
        try:
            rel = canonical_target.relative_to(canonical_root)
            if not str(rel).startswith(".."):
                return canonical_target
        except ValueError:
            pass

    raise FsSandboxDeniedError(
        f"Path escape denied: '{target_path}' (canonical: '{canonical_target}') "
        f"is outside workspace root '{workspace_root}' (canonical: '{canonical_root}')"
    )


def is_path_contained(target_path: str | Path, workspace_root: str | Path) -> bool:
    """Check whether target_path is strictly within workspace_root without raising.

    Returns:
        True if contained, False otherwise.
    """
    try:
        assert_path_contained(target_path, workspace_root)
        return True
    except (FsSandboxDeniedError, PermissionError, ValueError):
        return False
