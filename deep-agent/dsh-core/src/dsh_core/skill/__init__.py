"""Skill, workspace instruction, and system prompt subsystem for dsh-core.

Provides skill discovery and loading (`@deepseek-ai/dsh-skill`, `@deepseek-ai/dsh-skill-filesystem`),
workspace `AGENTS.md`/`CLAUDE.md` instruction loading and `@file` reference resolution
(`@deepseek-ai/dsh-agent-instructions`, `@deepseek-ai/dsh-file-reference-local`),
and KV-cache friendly system prompt assembly (`@deepseek-ai/dsh-system-prompt`).
"""

from .instructions import FileReferenceResolver, InstructionLoader
from .skill_registry import (
    FilesystemSkillProvider,
    SkillDocument,
    SkillRegistry,
    parse_skill_markdown,
)
from .system_prompt import PromptSection, SystemPromptBuilder

__all__ = [
    "SkillDocument",
    "FilesystemSkillProvider",
    "SkillRegistry",
    "parse_skill_markdown",
    "InstructionLoader",
    "FileReferenceResolver",
    "PromptSection",
    "SystemPromptBuilder",
]
