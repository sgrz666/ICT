"""Core file management primitives.

Provides windowed reading with line numbers, atomic writes via lock and staging,
exact string replacement editing, and directory listing within a contained workspace.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from .containment import (
    FsNotFoundError,
    assert_path_contained,
)
from .diff import generate_context_diff
from .observation import FsObservationPolicy
from .str_replace import StrReplaceEditor


class FileManager:
    """Manages workspace file I/O operations with containment, observation guards, and concurrency safety."""

    def __init__(
        self,
        workspace_root: str | Path,
        enforce_containment: bool = True,
        enforce_observation: bool = False,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.enforce_containment = enforce_containment
        self.observation_policy = FsObservationPolicy(enabled=enforce_observation)
        self._locks: dict[str, threading.RLock] = {}
        self._global_lock = threading.Lock()

    def _get_file_lock(self, path: Path) -> threading.RLock:
        """Get or create an in-memory lock for a canonical file path."""
        key = os.path.normcase(str(path.resolve()))
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.RLock()
            return self._locks[key]

    def _resolve(self, path: str | Path) -> Path:
        """Resolve path and optionally verify workspace containment."""
        raw_path = Path(path)
        if not raw_path.is_absolute():
            target = self.workspace_root / raw_path
        else:
            target = raw_path

        if self.enforce_containment:
            return assert_path_contained(target, self.workspace_root)
        return target.resolve()

    def exists(self, path: str | Path) -> bool:
        """Check if path exists within workspace."""
        try:
            target = self._resolve(path)
            return target.exists()
        except Exception:
            return False

    def read_text(
        self,
        path: str | Path,
        offset: int = 1,
        limit: int | None = None,
        with_line_numbers: bool = True,
        encoding: str = "utf-8",
    ) -> tuple[str, int]:
        """Read text from file with optional line offset, limit, and line numbers.

        Args:
            path: Relative or absolute path to file.
            offset: 1-indexed starting line number (default 1).
            limit: Maximum number of lines to read. None means read to end.
            with_line_numbers: If True, prefix lines with '{line_no}: '.
            encoding: Text encoding (default 'utf-8').

        Returns:
            A tuple of (formatted_text, total_line_count).

        Raises:
            FsNotFoundError: If file does not exist.
        """
        target = self._resolve(path)
        if not target.is_file():
            self.observation_policy.observe_path(target)
            raise FsNotFoundError(f"File not found: {path} (resolved: {target})")

        lock = self._get_file_lock(target)
        with lock:
            self.observation_policy.observe_path(target)
            with open(target, "r", encoding=encoding, errors="replace", newline="") as f:
                lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(0, offset - 1)
        if limit is not None:
            end_idx = min(total_lines, start_idx + max(0, limit))
        else:
            end_idx = total_lines

        selected_lines = lines[start_idx:end_idx]

        if with_line_numbers:
            formatted_lines = [
                f"{start_idx + idx + 1}: {line}"
                for idx, line in enumerate(selected_lines)
            ]
            return "".join(formatted_lines), total_lines
        else:
            return "".join(selected_lines), total_lines

    def write_text(
        self,
        path: str | Path,
        content: str,
        atomic: bool = True,
        encoding: str = "utf-8",
    ) -> int:
        """Write text to file, ensuring atomic publication and directory creation.

        Args:
            path: Target file path.
            content: Text content to write.
            atomic: If True, write to a temporary sibling file first and rename atomically.
            encoding: Text encoding (default 'utf-8').

        Returns:
            Number of bytes written.
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        lock = self._get_file_lock(target)
        with lock:
            self.observation_policy.check_write_intent(target)
            encoded_bytes = content.encode(encoding)
            if not atomic:
                with open(target, "w", encoding=encoding) as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                self.observation_policy.observe_path(target)
                return len(encoded_bytes)

            # Atomic staging in the same parent directory ensures same filesystem
            staging_prefix = f".dsh_tmp_{target.name}_"
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=staging_prefix,
                dir=target.parent,
                delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)
                try:
                    tmp.write(encoded_bytes)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                except Exception:
                    tmp_path.unlink(missing_ok=True)
                    raise

            # Atomic replace (works on POSIX and Windows in Python 3.3+, with retry for transient file locks)
            last_err = None
            for attempt in range(15):
                try:
                    os.replace(tmp_path, target)
                    break
                except (PermissionError, OSError) as e:
                    last_err = e
                    time.sleep(0.01 * (attempt + 1))
            else:
                tmp_path.unlink(missing_ok=True)
                if last_err:
                    raise last_err

            self.observation_policy.observe_path(target)
            return len(encoded_bytes)

    def edit_text(
        self,
        path: str | Path,
        old_str: str,
        new_str: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> tuple[str, str]:
        """Perform exact string replacement and return (new_content, unified_diff).

        Args:
            path: File to edit.
            old_str: Exact substring to find.
            new_str: Substring replacement.
            replace_all: Whether to replace all occurrences.
            encoding: Text encoding.

        Returns:
            A tuple of (new_content, diff_text).
        """
        target = self._resolve(path)
        if not target.is_file():
            raise FsNotFoundError(f"File not found for edit: {path}")

        lock = self._get_file_lock(target)
        with lock:
            self.observation_policy.check_edit_intent(target)
            with open(target, "r", encoding=encoding, errors="replace", newline="") as f:
                original_content = f.read()

            new_content = StrReplaceEditor.replace_exact(
                original_content,
                old_str=old_str,
                new_str=new_str,
                replace_all=replace_all,
            )

            rel_display = str(target.relative_to(self.workspace_root)).replace("\\", "/")
            diff_text = generate_context_diff(original_content, new_content, filename=rel_display)

            # Write back
            self.write_text(target, new_content, atomic=True, encoding=encoding)
            return new_content, diff_text

    def delete_file(self, path: str | Path) -> bool:
        """Delete a file within the workspace.

        Returns:
            True if deleted, False if did not exist.
        """
        target = self._resolve(path)
        lock = self._get_file_lock(target)
        with lock:
            if not target.exists():
                self.observation_policy.observe_path(target)
                return False
            if target.is_file():
                target.unlink()
                self.observation_policy.observe_path(target)
                return True
            return False

    def list_dir(
        self,
        path: str | Path = ".",
        recursive: bool = False,
        max_depth: int | None = None,
    ) -> list[dict[str, Any]]:
        """List files and directories in path.

        Args:
            path: Target directory path.
            recursive: If True, recursively list children.
            max_depth: Maximum directory depth for recursion.

        Returns:
            List of dicts: {"name": str, "path": str, "is_dir": bool, "size": int, "mtime": float}.
        """
        target = self._resolve(path)
        if not target.is_dir():
            raise FsNotFoundError(f"Directory not found: {path}")

        results: list[dict[str, Any]] = []

        if not recursive:
            for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                stat = item.stat()
                rel_path = str(item.relative_to(self.workspace_root)).replace("\\", "/")
                results.append({
                    "name": item.name,
                    "path": rel_path,
                    "is_dir": item.is_dir(),
                    "size": stat.st_size if item.is_file() else 0,
                    "mtime": stat.st_mtime,
                })
        else:
            base_parts_len = len(target.parts)
            for root, dirs, files in os.walk(target):
                current_depth = len(Path(root).parts) - base_parts_len
                if max_depth is not None and current_depth >= max_depth:
                    dirs.clear()

                for d in sorted(dirs):
                    item = Path(root) / d
                    stat = item.stat()
                    results.append({
                        "name": item.name,
                        "path": str(item.relative_to(self.workspace_root)).replace("\\", "/"),
                        "is_dir": True,
                        "size": 0,
                        "mtime": stat.st_mtime,
                    })

                for f in sorted(files):
                    item = Path(root) / f
                    try:
                        stat = item.stat()
                        results.append({
                            "name": item.name,
                            "path": str(item.relative_to(self.workspace_root)).replace("\\", "/"),
                            "is_dir": False,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        })
                    except (OSError, PermissionError):
                        continue

        return results
