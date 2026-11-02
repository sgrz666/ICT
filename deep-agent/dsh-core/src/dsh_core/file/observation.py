"""Filesystem observation policy module (@deepseek-ai/dsh-fs-observation-policy).

Implements the read-before-write / read-before-edit guard and Compare-And-Swap (CAS)
freshness checks over per-session observed file state:
- Editing an existing file requires having read it first (`FS_NOT_OBSERVED`).
- Overwriting an existing file with `write` requires having read it first (`FS_NOT_OBSERVED`);
  creating a brand-new file that does not yet exist on disk is permitted (`createIfAbsent`).
- If a file was modified externally after being read, `write`/`edit` rejects with `FS_STALE`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .containment import FsError, FsNotFoundError


class FsNotObservedError(FsError):
    """Raised when attempting to edit or overwrite a file before reading it (FS_NOT_OBSERVED)."""


class FsStaleFileError(FsError):
    """Raised when a file on disk has changed since the agent last observed it (FS_STALE)."""


@dataclass(frozen=True)
class FsVersion:
    """Point-in-time fingerprint of an observed file for CAS freshness checks."""

    mtime_ns: int
    size: int
    sha256: str

    @classmethod
    def from_path(cls, path: Path) -> FsVersion:
        """Compute the current FsVersion of a file on disk."""
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return cls(mtime_ns=stat.st_mtime_ns, size=stat.st_size, sha256=digest)


@dataclass(frozen=True)
class FsObservation:
    """Recorded observation of a target path (either present with version, or confirmed absent)."""

    kind: Literal["present", "absent"]
    version: FsVersion | None = None


class FsObservationPolicy:
    """Per-session observed-file state gate enforcing read-before-write and CAS freshness."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._observed: dict[str, FsObservation] = {}

    @staticmethod
    def _key(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    def clear(self) -> None:
        """Drop all recorded observations."""
        self._observed.clear()

    def observe_path(self, path: Path) -> FsObservation:
        """Inspect path on disk and record its authoritative present or absent state."""
        key = self._key(path)
        if path.is_file():
            obs = FsObservation(kind="present", version=FsVersion.from_path(path))
        else:
            obs = FsObservation(kind="absent", version=None)
        self._observed[key] = obs
        return obs

    def get_observation(self, path: Path) -> FsObservation | None:
        """Retrieve recorded observation for path, if any."""
        return self._observed.get(self._key(path))

    def check_write_intent(self, path: Path) -> Literal["createIfAbsent", "replaceIfVersion"]:
        """Validate write intent against prior observation and current disk state.

        - If unseen or confirmed absent: requires file not to exist on disk (`createIfAbsent`),
          otherwise raises `FsNotObservedError`.
        - If confirmed present: verifies current file content hash matches observed version
          (`replaceIfVersion`), otherwise raises `FsStaleFileError`.
        """
        if not self.enabled:
            return "replaceIfVersion" if path.exists() else "createIfAbsent"

        prior = self.get_observation(path)
        if prior is None or prior.kind == "absent":
            if path.exists():
                raise FsNotObservedError(
                    f'write to existing file "{path.name}" requires reading it first (FS_NOT_OBSERVED)'
                )
            return "createIfAbsent"

        # prior.kind == "present"
        if not path.exists():
            return "createIfAbsent"

        current_ver = FsVersion.from_path(path)
        if prior.version is not None and current_ver.sha256 != prior.version.sha256:
            raise FsStaleFileError(
                f'cannot write "{path.name}": file was modified externally since last read (FS_STALE)'
            )
        return "replaceIfVersion"

    def check_edit_intent(self, path: Path) -> FsVersion:
        """Validate edit intent against prior observation and current disk state.

        - Unseen rejects with `FsNotObservedError` (`FS_NOT_OBSERVED`).
        - Confirmed absence rejects with `FsNotFoundError` (`FS_NOT_FOUND`).
        - Presence verifies CAS version against current disk state (`FS_STALE`).
        """
        if not path.is_file():
            raise FsNotFoundError(f'cannot edit "{path.name}": file not found (FS_NOT_FOUND)')

        if not self.enabled:
            return FsVersion.from_path(path)

        prior = self.get_observation(path)
        if prior is None:
            raise FsNotObservedError(
                f'edit requires reading "{path.name}" first (FS_NOT_OBSERVED)'
            )
        if prior.kind == "absent" or prior.version is None:
            raise FsNotFoundError(f'cannot edit "{path.name}": observed as absent (FS_NOT_FOUND)')

        current_ver = FsVersion.from_path(path)
        if current_ver.sha256 != prior.version.sha256:
            raise FsStaleFileError(
                f'cannot edit "{path.name}": file was modified externally since last read (FS_STALE)'
            )
        return prior.version
