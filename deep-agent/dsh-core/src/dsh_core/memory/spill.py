"""Spill storage and retention policy (@deepseek-ai/dsh-spill-local, @deepseek-ai/dsh-spill-policy, @deepseek-ai/dsh-compaction-image-offload).

Ensures that oversized tool outputs exceeding `max_inline_tokens` are first persisted
losslessly to disk (`SpillStore`) before being bounded into `head + [...] + tail + SpillNotice`
for model consumption, preventing permanent information loss during tool result retention.
Also provides `ImageOffloadPolicy` for replacing over-budget historical images on the surface.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .token_meter import TokenMeter

if TYPE_CHECKING:
    from ..session.state_machine import Session


class SpillRef(BaseModel):
    """Reference to a spilled tool output file on disk."""

    spill_id: str
    session_id: str
    tool_name: str
    call_id: str
    path: str
    total_bytes: int
    sha256: str


class SpillStore:
    """Local filesystem spill backend (@deepseek-ai/dsh-spill-local)."""

    def __init__(self, spill_root: str | Path):
        self.spill_root = Path(spill_root).resolve()
        self.spill_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(raw: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return cleaned or "output"

    def save_text(
        self,
        session_id: str,
        tool_name: str,
        call_id: str,
        content: str,
        suggested_name: str | None = None,
    ) -> SpillRef:
        """Persist full tool output text to disk and return its SpillRef."""
        session_dir = self.spill_root / self._safe_name(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        ext_name = self._safe_name(suggested_name or f"{tool_name}.txt")
        if not ext_name.endswith(".txt") and "." not in ext_name:
            ext_name += ".txt"

        filename = f"{self._safe_name(call_id)}_{ext_name}"
        file_path = session_dir / filename
        raw_bytes = content.encode("utf-8")
        file_path.write_bytes(raw_bytes)

        digest = hashlib.sha256(raw_bytes).hexdigest()
        spill_id = f"spill_{digest[:12]}"
        return SpillRef(
            spill_id=spill_id,
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            path=str(file_path).replace("\\", "/"),
            total_bytes=len(raw_bytes),
            sha256=digest,
        )


def format_spill_notice(omitted_bytes: int, ref: SpillRef) -> str:
    """Format the official recoverable spill footer notice."""
    return (
        f"[Spill Notice: {omitted_bytes} bytes omitted from inline tool result; "
        f'full output ({ref.total_bytes} bytes) saved to "{ref.path}". '
        f"Use read_file or grep_search on that path to inspect the omitted content.]"
    )


class SpillPolicy:
    """Token-budgeted tool result retention policy (@deepseek-ai/dsh-spill-policy)."""

    GAP_MARKER = "\n\n[...]\n\n"

    def __init__(
        self,
        spill_store: SpillStore,
        max_inline_tokens: int = 12500,
        head_ratio: float = 0.75,
        token_meter: TokenMeter | None = None,
    ):
        if max_inline_tokens < 50:
            raise ValueError(f"max_inline_tokens must be >= 50 (got {max_inline_tokens})")
        self.spill_store = spill_store
        self.max_inline_tokens = max_inline_tokens
        self.head_ratio = max(0.1, min(0.9, head_ratio))
        self.meter = token_meter or TokenMeter()

    def bound_tool_result(
        self,
        content: str,
        session_id: str,
        tool_name: str,
        call_id: str,
    ) -> tuple[str, SpillRef | None]:
        """Bound a tool result to `max_inline_tokens`, spilling full text to disk if exceeded.

        Returns:
            Tuple of (retained_text, spill_ref_or_none).
        """
        estimated_tokens = self.meter.estimate_text(content)
        if estimated_tokens <= self.max_inline_tokens:
            return content, None

        ref = self.spill_store.save_text(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            content=content,
        )

        # Convert token budget into character budget (4 chars/token)
        max_chars = int(self.max_inline_tokens * TokenMeter.CHARS_PER_TOKEN)
        worst_notice = format_spill_notice(ref.total_bytes, ref)
        reserved_chars = len(self.GAP_MARKER) + len(worst_notice) + 4
        retain_budget_chars = int(max(40, max_chars - reserved_chars))

        head_chars = int(retain_budget_chars * self.head_ratio)
        tail_chars = int(max(10, retain_budget_chars - head_chars))

        head_text = content[:head_chars]
        tail_text = content[-tail_chars:] if tail_chars > 0 else ""
        omitted_chars = max(0, len(content) - len(head_text) - len(tail_text))
        omitted_bytes = len(content[head_chars : len(content) - tail_chars].encode("utf-8")) if omitted_chars > 0 else 0

        footer = format_spill_notice(omitted_bytes, ref)
        bounded = f"{head_text}{self.GAP_MARKER}{tail_text}\n\n{footer}"
        return bounded, ref


class ImageOffloadPolicy:
    """Durable image offload policy (@deepseek-ai/dsh-compaction-image-offload).

    When active surface messages contain more than `max_images` image references/attachments,
    replaces the oldest image entries on the surface with lightweight text placeholders and
    appends an `image/offload` audit event.
    """

    def __init__(self, max_active_images: int = 4):
        self.max_active_images = max(1, max_active_images)

    def offload_if_needed(self, session: Session) -> int:
        """Scan active surface for image blocks/attachments and offload oldest beyond budget."""
        active_seqs = session.surface_manager.get_active_seqs()
        image_seqs: list[int] = []

        for seq in active_seqs:
            if seq < len(session.log):
                ev = session.log[seq]
                data = ev.data or {}
                if data.get("has_image") or "images" in data or "[Image:" in str(data.get("content", "")):
                    image_seqs.append(seq)

        if len(image_seqs) <= self.max_active_images:
            return 0

        to_offload = image_seqs[: len(image_seqs) - self.max_active_images]
        for seq in to_offload:
            ev = session.log[seq]
            old_content = str(ev.data.get("content", ""))
            img_id = ev.data.get("image_id", f"img_seq_{seq}")
            placeholder = (
                f"[Image Offloaded: attachment {img_id} at seq {seq} was offloaded from active "
                f"context to stay within visual token budget.]"
            )
            ev.data["content"] = f"{old_content}\n{placeholder}".strip()
            ev.data.pop("images", None)
            ev.data["has_image"] = False
            ev.data["image_offloaded"] = True

        session.append(
            "image/offload",
            {
                "offloaded_seqs": to_offload,
                "offloaded_count": len(to_offload),
                "max_active_images": self.max_active_images,
            },
        )
        return len(to_offload)
