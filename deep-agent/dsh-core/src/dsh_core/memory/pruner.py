"""Tool output middle-omission pruner.

Truncates oversized tool execution results (compiler logs, large file reads,
recursive directory dumps) before invoking LLM summarization, saving tokens
deterministically at zero computational cost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..session.state_machine import Session


class OutputPruner:
    """Performs deterministic middle-omission truncation on oversized tool outputs."""

    def __init__(
        self,
        threshold_chars: int = 4000,
        head_chars: int = 1500,
        tail_chars: int = 1500,
    ):
        self.threshold_chars = threshold_chars
        self.head_chars = head_chars
        self.tail_chars = tail_chars

    def prune_text(
        self,
        text: str,
        threshold: int | None = None,
        head: int | None = None,
        tail: int | None = None,
    ) -> tuple[str, bool, int]:
        """Truncate text with middle omission if length exceeds threshold.

        Args:
            text: Input string.
            threshold: Character threshold (default: instance threshold_chars).
            head: Characters to preserve from beginning (default: instance head_chars).
            tail: Characters to preserve from end (default: instance tail_chars).

        Returns:
            Tuple of (pruned_text, was_pruned, characters_omitted).
        """
        eff_threshold = threshold if threshold is not None else self.threshold_chars
        eff_head = head if head is not None else self.head_chars
        eff_tail = tail if tail is not None else self.tail_chars

        if len(text) <= eff_threshold:
            return text, False, 0

        # Ensure head + tail does not exceed text length
        if eff_head + eff_tail >= len(text):
            return text, False, 0

        omitted = len(text) - (eff_head + eff_tail)
        marker = f"\n\n[... {omitted} characters omitted ...]\n\n"
        pruned = text[:eff_head] + marker + text[-eff_tail:]
        return pruned, True, omitted

    def prune_tool_results(
        self,
        session: Session,
        threshold_chars: int | None = None,
    ) -> int:
        """Inspect active surface tool/results in session and prune oversized ones in-place.

        Args:
            session: Active Session instance.
            threshold_chars: Optional override for pruning threshold.

        Returns:
            Number of tool result nodes pruned.
        """
        active_seqs = session.surface_manager.get_active_seqs()
        pruned_count = 0

        for seq in active_seqs:
            if seq >= len(session.log):
                continue
            event = session.log[seq]
            if event.type != "tool/result":
                continue

            content = event.data.get("content", "")
            pruned_content, was_pruned, omitted = self.prune_text(
                content,
                threshold=threshold_chars,
            )

            if was_pruned:
                # Append compaction/prune record in log
                session.append(
                    "compaction/prune",
                    {
                        "target_seq": seq,
                        "original_chars": len(content),
                        "pruned_chars": len(pruned_content),
                        "omitted_chars": omitted,
                    },
                    ignorable=True,
                )

                # In-place replace the tool/result surface node
                updated_data = dict(event.data)
                updated_data["content"] = pruned_content

                session.append(
                    "tool/result",
                    updated_data,
                    surface_op="replace",
                    replace_range=(seq, seq),
                    source_event_seqs=event.source_event_seqs,
                )
                pruned_count += 1

        return pruned_count
