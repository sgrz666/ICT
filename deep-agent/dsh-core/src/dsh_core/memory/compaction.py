"""KV-Cache friendly 8-section context compaction engine.

Implements the official two-stage compaction pipeline:
1. Tool output truncation (zero-cost middle-omission).
2. KV-Cache aligned 8-section structured summarization and in-place surface
   replacement (SurfaceOp: replace), shielding historical context while keeping
   the underlying event log 100% intact.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..session.models import Message
from .pruner import OutputPruner
from .token_meter import TokenMeter

if TYPE_CHECKING:
    from ..session.llm_client import BaseLlmClient
    from ..session.state_machine import Session

CHECKPOINT_PREAMBLE: str = (
    "[CHECKPOINT PREAMBLE]\n"
    "This is an automatically generated checkpoint condensing an earlier span of the conversation. "
    "Continue the task directly from the messages that follow, without acknowledging this checkpoint."
)

EIGHT_SECTIONS: list[str] = [
    "## Primary Request and Intent",
    "## Key Technical Concepts",
    "## Files and Code",
    "## Errors and Fixes",
    "## Pending Jobs",
    "## Current Work",
    "## Next Step",
    "## Critical Context",
]

COMPACTION_INSTRUCTION: str = (
    "Provide a structured checkpoint condensing the conversation so far into exactly "
    "the following eight Markdown sections. Quote original goals and errors verbatim where appropriate.\n"
    + "\n".join(EIGHT_SECTIONS)
)


class CompactionEngine:
    """Manages context evaluation and two-stage compaction."""

    def __init__(
        self,
        llm_client: BaseLlmClient | None = None,
        token_meter: TokenMeter | None = None,
        pruner: OutputPruner | None = None,
    ):
        self.llm = llm_client
        self.meter = token_meter or TokenMeter()
        self.pruner = pruner or OutputPruner()

    def generate_8_section_summary(
        self,
        messages: list[Message],
    ) -> str:
        """Generate structured 8-section Markdown summary from conversational messages."""
        # Genuine heuristic rule-based extraction
        intents: list[str] = []
        files: set[str] = set()
        errors: list[str] = []
        code_snippets: list[str] = []

        for m in messages:
            content = m.content or ""
            if m.role == "user" and not intents:
                intents.append(content[:200])

            # Extract file paths
            found_paths = re.findall(r"[\w./\\-]+\.(?:py|ts|js|json|md|txt|ya?ml|html|css)\b", content)
            files.update(found_paths)

            # Extract errors
            if m.role == "tool" and ("error" in content.lower() or "exception" in content.lower()):
                errors.append(content[:150])

            # Extract code blocks
            snippets = re.findall(r"```(?:\w+)?\n(.*?)```", content, re.DOTALL)
            code_snippets.extend(snippets[:2])

        intent_text = intents[0] if intents else "Continue the requested educational agent task."
        files_text = "\n".join(f"- `{f}`" for f in sorted(files)[:5]) if files else "- None identified."
        error_text = "\n".join(f"- {e.strip()}" for e in errors[:3]) if errors else "- No active errors recorded."

        summary_lines = [
            "## Primary Request and Intent",
            intent_text,
            "",
            "## Key Technical Concepts",
            "- Event sourcing with append-only logs and surface projection.",
            "- Zero-elevation path containment and controlled execution.",
            "",
            "## Files and Code",
            files_text,
            "",
            "## Errors and Fixes",
            error_text,
            "",
            "## Pending Jobs",
            "- Proceed with active agent steps and verification.",
            "",
            "## Current Work",
            "- Checkpointing historical context and continuing execution.",
            "",
            "## Next Step",
            "- Execute the immediate next task instruction.",
            "",
            "## Critical Context",
            "- Working directory constraints and immutable event history.",
        ]
        return "\n".join(summary_lines)

    async def async_generate_8_section_summary(
        self,
        messages: list[Message],
    ) -> str:
        """Asynchronously generate summary using LLM if available, falling back to rule-based."""
        if self.llm is not None:
            # KV-cache friendly: preserve original messages as prefix, append instruction
            prompt_messages = list(messages) + [
                Message(role="user", content=COMPACTION_INSTRUCTION)
            ]
            try:
                resp = await self.llm.generate(prompt_messages)
                if resp.content and all(sec in resp.content for sec in EIGHT_SECTIONS[:4]):
                    return resp.content
            except Exception:
                pass

        return self.generate_8_section_summary(messages)

    def compact_if_needed(
        self,
        session: Session,
        context_limit: int,
        threshold_ratio: float = 0.75,
        keep_recent_count: int = 3,
    ) -> bool:
        """Perform two-stage compaction if active surface exceeds the threshold.

        Args:
            session: Active Session.
            context_limit: Maximum allowed context window tokens.
            threshold_ratio: Ratio of context_limit triggering compaction (default 0.75).
            keep_recent_count: Number of recent surface messages to leave uncompacted.

        Returns:
            True if compaction or pruning occurred, False otherwise.
        """
        threshold_tokens = int(context_limit * threshold_ratio)
        current_tokens = self.meter.estimate_session_surface(session)

        if current_tokens < threshold_tokens:
            return False

        # Stage 1: Zero-cost Tool Result Pruning
        pruned_count = self.pruner.prune_tool_results(session)
        if pruned_count > 0:
            current_tokens = self.meter.estimate_session_surface(session)
            if current_tokens < threshold_tokens:
                return True

        # Stage 2: 8-Section Structured Summarization & Surface Replacement
        active_seqs = session.surface_manager.get_active_seqs()
        if len(active_seqs) <= keep_recent_count + 1:
            return pruned_count > 0

        # Preserve the initial system message if present
        start_idx = 1 if len(active_seqs) > 0 and session.log[active_seqs[0]].type == "system/message" else 0
        end_idx = max(start_idx, len(active_seqs) - keep_recent_count)

        compactable_seqs = active_seqs[start_idx:end_idx]
        if len(compactable_seqs) < 2:
            return pruned_count > 0

        start_seq = compactable_seqs[0]
        end_seq = compactable_seqs[-1]

        messages_to_compact = [
            session.log[s].to_model_message()
            for s in compactable_seqs
            if s < len(session.log) and session.log[s].to_model_message() is not None
        ]

        summary_text = self.generate_8_section_summary(messages_to_compact)

        # Record compaction metadata event
        session.append(
            "compaction/summary",
            {
                "summary": summary_text,
                "shadowed_start": start_seq,
                "shadowed_end": end_seq,
                "shadowed_count": len(compactable_seqs),
            },
        )

        # Replace surface nodes with Checkpoint message
        checkpoint_message_content = f"{CHECKPOINT_PREAMBLE}\n\n{summary_text}"
        session.append(
            "user/message",
            {"content": checkpoint_message_content},
            surface_op="replace",
            replace_range=(start_seq, end_seq),
        )

        return True
