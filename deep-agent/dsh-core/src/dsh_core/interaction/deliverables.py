"""Deliverable presentation and per-turn workspace change tracker (@deepseek-ai/dsh-tool-present & @deepseek-ai/dsh-workspace-changes).

Records explicit file deliverables (`present` tool) and snapshots the workspace
working tree before and after each turn to emit `workspace/changes` events
listing created, modified, and deleted files.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..file.containment import FsNotFoundError, assert_path_contained

if TYPE_CHECKING:
    from ..session.state_machine import Session


class DeliverableItem(BaseModel):
    """Explicit workspace file deliverable declared via the `present` tool."""

    path: str
    title: str
    description: str = ""
    size_bytes: int = 0


class TurnWorkspaceChanges(BaseModel):
    """Per-turn file changes detected in the workspace root."""

    turn: int
    created: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.created or self.modified or self.deleted)


class DeliverableManager:
    """Manages explicit workspace deliverables declared by the agent (`present`)."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self._deliverables: dict[str, list[DeliverableItem]] = {}

    def present(
        self,
        session: Session,
        path: str | Path,
        title: str,
        description: str = "",
    ) -> DeliverableItem:
        """Validate that `path` exists inside `workspace_root` and record a `deliverable/present` event."""
        raw_p = Path(path)
        target = raw_p if raw_p.is_absolute() else (self.workspace_root / raw_p)
        resolved = assert_path_contained(target, self.workspace_root)
        if not resolved.is_file():
            raise FsNotFoundError(f"present: deliverable file not found: {path}")

        rel_path = str(resolved.relative_to(self.workspace_root)).replace("\\", "/")
        item = DeliverableItem(
            path=rel_path,
            title=title.strip() or resolved.name,
            description=description.strip(),
            size_bytes=resolved.stat().st_size,
        )
        self._deliverables.setdefault(session.session_id, []).append(item)
        session.append("deliverable/present", item.model_dump())
        return item

    def list_deliverables(self, session_id: str) -> list[DeliverableItem]:
        """Return all deliverables presented in `session_id`."""
        return list(self._deliverables.get(session_id, []))


class WorkspaceChangeTracker:
    """Snapshots workspace files to compute per-turn created/modified/deleted sets."""

    IGNORE_DIRS = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".venv",
        "dist",
        ".sessions",
        "spills",
        ".dsh_spills",
    }

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self._baseline: dict[str, str] = {}

    def snapshot(self) -> dict[str, str]:
        """Compute `{rel_path: sha256}` map for all files in `workspace_root`."""
        state: dict[str, str] = {}
        if not self.workspace_root.is_dir():
            return state

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [
                d
                for d in dirs
                if d not in self.IGNORE_DIRS and not d.startswith(".dsh_tmp_")
            ]
            for fname in files:
                if fname.startswith(".dsh_tmp_"):
                    continue
                fpath = Path(root) / fname
                try:
                    rel = str(fpath.relative_to(self.workspace_root)).replace("\\", "/")
                    digest = hashlib.sha256(fpath.read_bytes()).hexdigest()
                    state[rel] = digest
                except Exception:
                    pass
        return state

    def begin_turn(self) -> dict[str, str]:
        """Capture baseline workspace state at turn start."""
        self._baseline = self.snapshot()
        return self._baseline

    def end_turn(self, session: Session, turn: int = 1) -> TurnWorkspaceChanges:
        """Compare current workspace state against baseline and log `workspace/changes` if non-empty."""
        after = self.snapshot()
        before = self._baseline

        created = sorted(k for k in after if k not in before)
        deleted = sorted(k for k in before if k not in after)
        modified = sorted(k for k in after if k in before and after[k] != before[k])

        changes = TurnWorkspaceChanges(
            turn=turn,
            created=created,
            modified=modified,
            deleted=deleted,
        )
        if changes.has_changes:
            session.append("workspace/changes", changes.model_dump())

        self._baseline = after
        return changes
