"""Modular system prompt assembly registry (@deepseek-ai/dsh-system-prompt).

Composes priority-ordered prompt sections (persona, workspace instructions,
skill catalog, plan mode, labkit guidance) and supports `in_history` updates
that preserve the initial system prompt prefix for KV-Cache reuse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..session.state_machine import Session


class PromptSection(BaseModel):
    """A named, priority-ordered section in the composed system prompt."""

    id: str
    content: str
    priority: int = 100


class SystemPromptBuilder:
    """Assembles and updates the agent's system prompt sections."""

    def __init__(self, persona_prefix: str = "You are the ICT EduForge AI Agent (启智AGENT)."):
        self._sections: dict[str, PromptSection] = {}
        if persona_prefix.strip():
            self.set_section("persona", persona_prefix.strip(), priority=10)

    def set_section(self, section_id: str, content: str, priority: int = 100) -> None:
        """Register or update a prompt section."""
        cleaned = content.strip()
        if not cleaned:
            self._sections.pop(section_id, None)
            return
        self._sections[section_id] = PromptSection(
            id=section_id,
            content=cleaned,
            priority=priority,
        )

    def remove_section(self, section_id: str) -> None:
        """Remove a prompt section by id."""
        self._sections.pop(section_id, None)

    def build(self) -> str:
        """Assemble all registered sections sorted by `(priority, id)`."""
        ordered = sorted(self._sections.values(), key=lambda s: (s.priority, s.id))
        return "\n\n".join(s.content for s in ordered if s.content)

    def apply_to_session(
        self,
        session: Session,
        in_history_update: bool = True,
    ) -> str:
        """Ensure `session` has the current system prompt, preserving KV-cache prefix when updated."""
        assembled = self.build()
        active_seqs = session.surface_manager.get_active_seqs()

        # If session has no initial system message yet, append at seq 0 / current start
        has_system = any(
            s < len(session.log) and session.log[s].type == "system/message"
            for s in active_seqs
        )
        if not has_system:
            session.append(
                "system/message",
                {"role": "system", "content": assembled},
                surface_op="append",
            )
            return assembled

        # Find the most recent system prompt content
        latest_system_content = ""
        first_system_seq: int | None = None
        for s in active_seqs:
            if s < len(session.log) and session.log[s].type == "system/message":
                if first_system_seq is None:
                    first_system_seq = s
                latest_system_content = str(session.log[s].data.get("content", ""))

        if latest_system_content == assembled:
            return assembled

        if in_history_update:
            # Append updated system prompt at tail of history to keep cached prefix intact
            session.append(
                "system/message",
                {"role": "system", "content": assembled, "in_history": True},
                surface_op="append",
            )
        elif first_system_seq is not None:
            session.log[first_system_seq].data["content"] = assembled

        return assembled
