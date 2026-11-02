"""Append-only JSONL session persistence engine (Version 4 format).

Stores session history on disk conforming to the format version 4 specification:
- Line 1: SessionHeader metadata
- Line 2+: SessionEvent JSON records (append-only)
- Path safe encoding for workspace directory and session identifier.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import SESSION_FORMAT_VERSION, SessionEvent, SessionHeader


def project_key(cwd: str | Path) -> str:
    """Encode a workspace directory path into a filesystem-safe directory segment.

    Example: 'D:\\codeplus\\ICT' -> '--D-codeplus-ICT--'
    """
    normalized = str(Path(cwd).resolve()).replace("\\", "/")
    # Remove leading slashes and drive colons
    cleaned = re.sub(r"^[a-zA-Z]:", lambda m: m.group(0)[0].upper(), normalized)
    sanitized = re.sub(r"[/\\:\s]+", "-", cleaned).strip("-")
    return f"--{sanitized}--"


def encode_session_id(session_id: str) -> str:
    """Encode a session id to prevent path traversal and illegal filename characters."""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", session_id)
    return sanitized or "default-session"


class JsonlPersistence:
    """Handles atomic append-only JSONL file storage for a session."""

    def __init__(
        self,
        storage_root: str | Path,
        cwd: str | Path,
        session_id: str,
    ):
        self.storage_root = Path(storage_root).resolve()
        self.cwd = str(Path(cwd).resolve())
        self.session_id = session_id

        self.session_dir = (
            self.storage_root
            / project_key(self.cwd)
            / encode_session_id(self.session_id)
        )
        self.file_path = self.session_dir / "session.v4.jsonl"

    def exists(self) -> bool:
        """Check whether the persisted session file exists on disk."""
        return self.file_path.is_file()

    def init_session(self, header: SessionHeader) -> Path:
        """Initialize a new session file with its single header line.

        Args:
            header: SessionHeader instance.

        Returns:
            The Path to the initialized session.v4.jsonl file.
        """
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(header.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())
        return self.file_path

    def append_event(self, event: SessionEvent) -> None:
        """Append a single SessionEvent line to the session file.

        Args:
            event: SessionEvent instance.
        """
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())

    def load_session(self) -> tuple[SessionHeader, list[SessionEvent]]:
        """Load and parse session header and all recorded events from disk.

        Returns:
            A tuple of (SessionHeader, list[SessionEvent]).

        Raises:
            FileNotFoundError: If the session file does not exist.
            ValueError: If header or event data is malformed.
        """
        if not self.file_path.is_file():
            raise FileNotFoundError(f"Session file not found at: {self.file_path}")

        events: list[SessionEvent] = []
        header: SessionHeader | None = None

        with open(self.file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            raise ValueError(f"Empty session file at: {self.file_path}")

        # Parse Header Line (Line 0)
        first_line = lines[0].strip()
        header_data = json.loads(first_line)
        header = SessionHeader.model_validate(header_data)

        # Parse Event Lines (Line 1+)
        for line_no, line in enumerate(lines[1:], start=2):
            raw = line.strip()
            if not raw:
                continue
            event_data = json.loads(raw)
            event = SessionEvent.model_validate(event_data)
            events.append(event)

        return header, events
