"""Model-visible surface projection manager.

Maintains the ordered active list of message event sequence numbers exposed to
the model. Supports both appending new messages and in-place replacement of
historical message ranges (shadowing) during context compaction without mutating
the underlying append-only event log.
"""

from __future__ import annotations

from .models import SessionEvent


class SurfaceManager:
    """Manages the projected sequence of model-visible events."""

    def __init__(self, initial_nodes: list[int] | None = None):
        self._nodes: list[int] = list(initial_nodes) if initial_nodes is not None else []

    def get_active_seqs(self) -> list[int]:
        """Return a copy of currently active model-visible event sequence numbers."""
        return list(self._nodes)

    def apply(self, event: SessionEvent) -> None:
        """Apply an event's surface operation to update the active node list."""
        if not event.is_surface_eligible():
            return

        op = event.surface_op
        if op is None or op.op == "append":
            self._nodes.append(event.seq)
            return

        if op.op == "replace":
            start_seq = op.start_seq
            end_seq = op.end_seq

            if start_seq is None or end_seq is None:
                # If range is omitted, treat as replacement of the last node or append
                if self._nodes:
                    self._nodes[-1] = event.seq
                else:
                    self._nodes.append(event.seq)
                return

            # Find matching active nodes within [start_seq, end_seq]
            indices = [
                i for i, seq in enumerate(self._nodes)
                if start_seq <= seq <= end_seq
            ]

            if indices:
                min_idx = min(indices)
                max_idx = max(indices)
                # Replace the entire span [min_idx : max_idx + 1] with [event.seq]
                self._nodes[min_idx : max_idx + 1] = [event.seq]
            else:
                # Range not currently in surface, append as fallback
                self._nodes.append(event.seq)

    def reset(self, nodes: list[int] | None = None) -> None:
        """Reset the surface node projection."""
        self._nodes = list(nodes) if nodes is not None else []
