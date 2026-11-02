"""Workspace instruction loader and @file reference resolver (@deepseek-ai/dsh-agent-instructions & @deepseek-ai/dsh-file-reference-local).

Loads `AGENTS.md` / `CLAUDE.md` instruction files up to a configurable byte cap
(default 65,536 bytes) and resolves `@path/to/file` inline references within
user prompts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..file.manager import FileManager

_FILE_REF_RE = re.compile(r"(?:^|(?<=\s))@([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)\b")


class InstructionLoader:
    """Loads workspace `AGENTS.md` and `CLAUDE.md` instruction files."""

    INSTRUCTION_FILENAMES = ("AGENTS.md", "CLAUDE.md")

    def __init__(self, workspace_root: str | Path, max_bytes: int = 65536):
        self.workspace_root = Path(workspace_root).resolve()
        self.max_bytes = max(512, max_bytes)

    def load_instructions(self) -> str:
        """Read instruction files in `workspace_root` up to `max_bytes`."""
        chunks: list[str] = []
        remaining = self.max_bytes

        for fname in self.INSTRUCTION_FILENAMES:
            fpath = self.workspace_root / fname
            if fpath.is_file():
                raw = fpath.read_bytes()
                clipped = raw[:remaining].decode("utf-8", errors="replace").strip()
                if clipped:
                    chunks.append(f"<!-- {fname} -->\n{clipped}")
                    remaining -= len(raw)
                if remaining <= 0:
                    break

        return "\n\n".join(chunks)


class FileReferenceResolver:
    """Resolves `@file` references in user prompts using a contained FileManager."""

    def __init__(self, file_manager: FileManager, max_lines_per_file: int = 100):
        self.file_manager = file_manager
        self.max_lines_per_file = max(10, max_lines_per_file)

    def extract_references(self, prompt_text: str) -> list[str]:
        """Extract all `@path/to/file` references from `prompt_text`."""
        seen: list[str] = []
        for match in _FILE_REF_RE.finditer(prompt_text):
            ref = match.group(1)
            if ref not in seen:
                seen.append(ref)
        return seen

    def resolve_prompt_references(self, prompt_text: str) -> str:
        """Append resolved file snippets for any valid `@file` references in `prompt_text`."""
        refs = self.extract_references(prompt_text)
        if not refs:
            return prompt_text

        attachments: list[str] = []
        for ref in refs:
            if self.file_manager.exists(ref):
                try:
                    snippet, total = self.file_manager.read_text(
                        ref, offset=1, limit=self.max_lines_per_file, with_line_numbers=True
                    )
                    attachments.append(
                        f'<file_reference path="{ref}" total_lines="{total}">\n{snippet}</file_reference>'
                    )
                except Exception:
                    pass

        if not attachments:
            return prompt_text
        return prompt_text + "\n\n" + "\n\n".join(attachments)
