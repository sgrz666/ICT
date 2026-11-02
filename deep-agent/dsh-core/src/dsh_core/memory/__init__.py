"""Memory and context management subsystem for dsh-core.

Provides character/token density estimation, middle-omission tool output pruning,
and KV-cache friendly 8-section structured summarization with in-place surface replacement.
"""

from .compaction import (
    CHECKPOINT_PREAMBLE,
    COMPACTION_INSTRUCTION,
    EIGHT_SECTIONS,
    CompactionEngine,
)
from .pruner import OutputPruner
from .spill import (
    ImageOffloadPolicy,
    SpillPolicy,
    SpillRef,
    SpillStore,
    format_spill_notice,
)
from .token_meter import TokenMeter, TokenUsage

__all__ = [
    "TokenMeter",
    "TokenUsage",
    "OutputPruner",
    "SpillRef",
    "SpillStore",
    "SpillPolicy",
    "format_spill_notice",
    "ImageOffloadPolicy",
    "CompactionEngine",
    "CHECKPOINT_PREAMBLE",
    "EIGHT_SECTIONS",
    "COMPACTION_INSTRUCTION",
]
