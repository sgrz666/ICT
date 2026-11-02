"""Skill provider registry and filesystem loader (@deepseek-ai/dsh-skill, @deepseek-ai/dsh-skill-filesystem, @deepseek-ai/dsh-tool-skill).

Discovers `.agents/skills/*/SKILL.md` (and custom skill roots), parses YAML
frontmatter (`name`, `description`) and Markdown body, renders compact catalog
summaries for the system prompt, and loads full skill instructions on demand.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", re.DOTALL)


class SkillDocument(BaseModel):
    """Parsed representation of a skill (`SKILL.md`)."""

    name: str
    description: str
    body: str
    source_path: str


def parse_skill_markdown(text: str, fallback_name: str, source_path: str = "") -> SkillDocument:
    """Parse YAML frontmatter (`name`, `description`) and Markdown body from `SKILL.md`."""
    name = fallback_name
    description = f"Specialized workflow instructions for {fallback_name}."
    body = text.strip()

    match = _FRONTMATTER_RE.match(text)
    if match:
        fm_raw, body_raw = match.group(1), match.group(2)
        body = body_raw.strip()
        for line in fm_raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip().strip("'\"")
                if k == "name" and v:
                    name = v
                elif k == "description" and v:
                    description = v

    return SkillDocument(
        name=name,
        description=description,
        body=body,
        source_path=source_path,
    )


class FilesystemSkillProvider:
    """Discovers skills from local filesystem directories (`.agents/skills`, etc.)."""

    def __init__(self, search_dirs: list[str | Path]):
        self.search_dirs = [Path(d).resolve() for d in search_dirs]

    def discover(self) -> list[SkillDocument]:
        """Scan configured directories for `<skill_name>/SKILL.md` files."""
        found: list[SkillDocument] = []
        for root in self.search_dirs:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if child.is_dir():
                    skill_md = child / "SKILL.md"
                    if skill_md.is_file():
                        raw = skill_md.read_text(encoding="utf-8", errors="replace")
                        doc = parse_skill_markdown(
                            raw,
                            fallback_name=child.name,
                            source_path=str(skill_md).replace("\\", "/"),
                        )
                        found.append(doc)
        return found


class SkillRegistry:
    """Central registry of available agent skills."""

    def __init__(self):
        self._skills: dict[str, SkillDocument] = {}

    def register(self, skill: SkillDocument) -> None:
        """Register or override a skill document by name."""
        self._skills[skill.name] = skill

    def load_from_provider(self, provider: FilesystemSkillProvider) -> int:
        """Discover and register all skills from `provider`. Returns count registered."""
        docs = provider.discover()
        for doc in docs:
            self.register(doc)
        return len(docs)

    def list_skills(self) -> list[SkillDocument]:
        """Return all registered skills sorted by name."""
        return [self._skills[k] for k in sorted(self._skills.keys())]

    def get_skill(self, name: str) -> SkillDocument:
        """Retrieve a skill by name or raise KeyError."""
        if name not in self._skills:
            available = ", ".join(sorted(self._skills.keys())) or "none"
            raise KeyError(f'Unknown skill "{name}". Available skills: {available}')
        return self._skills[name]

    def format_catalog_section(self) -> str:
        """Render the compact skill catalog for injection into the system prompt."""
        skills = self.list_skills()
        if not skills:
            return ""
        lines = ["Available skills (call `load_skill` with the skill name to load full instructions):"]
        for s in skills:
            lines.append(f"- `{s.name}`: {s.description}")
        return "\n".join(lines)
