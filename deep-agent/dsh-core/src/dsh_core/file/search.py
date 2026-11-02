"""Pure-Python workspace search module.

Provides recursive grep (literal and regex) and glob pattern matching within
a workspace boundary, with automatic pruning of caches, build artifacts, and
binary files.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from .containment import assert_path_contained


class WorkspaceSearcher:
    """Pure-Python searcher for workspace files."""

    PRUNE_DIRS: set[str] = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        ".pytest_cache",
        ".dsh_staging",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }

    BINARY_EXTENSIONS: set[str] = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar",
        ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc",
        ".class", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4",
    }

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()

    def _is_binary(self, file_path: Path) -> bool:
        """Heuristic check for binary files."""
        if file_path.suffix.lower() in self.BINARY_EXTENSIONS:
            return True
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return True
        except (OSError, PermissionError):
            return True
        return False

    def grep(
        self,
        pattern: str,
        path: str | Path = ".",
        is_regex: bool = False,
        case_insensitive: bool = False,
        max_results: int = 100,
        glob_filter: str | None = None,
    ) -> list[dict[str, str | int]]:
        """Search text occurrences in files within path.

        Args:
            pattern: Search string or regex pattern.
            path: Target subdirectory or file relative to workspace root.
            is_regex: If True, compile pattern as regular expression.
            case_insensitive: If True, ignore case.
            max_results: Maximum matching lines to return.
            glob_filter: Optional file glob pattern to filter target files (e.g. '*.py').

        Returns:
            List of dicts: {"file": str, "line_number": int, "line": str}.
        """
        target_dir = assert_path_contained(self.workspace_root / path, self.workspace_root)

        flags = re.IGNORECASE if case_insensitive else 0
        if is_regex:
            regex = re.compile(pattern, flags)
        else:
            regex = re.compile(re.escape(pattern), flags)

        results: list[dict[str, str | int]] = []

        if target_dir.is_file():
            files_to_search = [target_dir]
        else:
            files_to_search = []
            for root, dirs, files in os.walk(target_dir):
                # Prune unwanted directories in-place
                dirs[:] = [d for d in dirs if d not in self.PRUNE_DIRS]
                for file_name in files:
                    if glob_filter and not fnmatch.fnmatch(file_name, glob_filter):
                        continue
                    files_to_search.append(Path(root) / file_name)

        for file_path in files_to_search:
            if len(results) >= max_results:
                break
            if self._is_binary(file_path):
                continue

            try:
                rel_file = str(file_path.relative_to(self.workspace_root)).replace("\\", "/")
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_idx, line in enumerate(f, start=1):
                        if regex.search(line):
                            results.append({
                                "file": rel_file,
                                "line_number": line_idx,
                                "line": line.rstrip("\r\n"),
                            })
                            if len(results) >= max_results:
                                break
            except (OSError, PermissionError):
                continue

        return results

    def glob(
        self,
        pattern: str,
        path: str | Path = ".",
    ) -> list[str]:
        """Find files matching a glob pattern relative to path.

        Args:
            pattern: Glob pattern (e.g. '**/*.py', 'src/*.ts').
            path: Base directory relative to workspace root.

        Returns:
            Sorted list of relative path strings.
        """
        base_dir = assert_path_contained(self.workspace_root / path, self.workspace_root)
        matches: list[str] = []

        if not base_dir.is_dir():
            return matches

        for item in base_dir.glob(pattern):
            # Check if any parent part matches PRUNE_DIRS
            parts = item.relative_to(self.workspace_root).parts
            if any(p in self.PRUNE_DIRS for p in parts):
                continue
            matches.append(str(item.relative_to(self.workspace_root)).replace("\\", "/"))

        return sorted(matches)
