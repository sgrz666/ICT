"""Tests for the dsh-core memory subsystem.

Covers:
- TokenMeter estimation (chars/token density, structural overheads, session surface)
- OutputPruner middle-omission (head/tail preservation, zero-cost deterministic truncation)
- CompactionEngine 8-section structured summarization and surface replacement
"""

from __future__ import annotations

import pytest

from dsh_core.memory import (
    CHECKPOINT_PREAMBLE,
    COMPACTION_INSTRUCTION,
    EIGHT_SECTIONS,
    CompactionEngine,
    OutputPruner,
    TokenMeter,
    TokenUsage,
)
from dsh_core.session import Message, Session, ToolCall


# ==============================================================================
# Tier 1: TokenMeter
# ==============================================================================


def test_token_meter_estimate_text():
    """Test text token estimation using the 4 chars/token heuristic."""
    meter = TokenMeter()

    assert meter.estimate_text("") == 0
    assert meter.estimate_text("1234") == 1
    assert meter.estimate_text("12345678") == 2
    assert meter.estimate_text("a" * 100) == 25


def test_token_meter_estimate_message():
    """Test estimating message token cost including role and structure overhead."""
    meter = TokenMeter()

    msg = Message(role="user", content="Hello world")
    tokens = meter.estimate_message(msg)
    # content: 11 chars -> 3 tokens; role: 'user' 4 chars -> 1 + 2 = 3; overhead: 4; total >= 10
    assert tokens >= 10

    # Message with tool calls
    msg_with_tools = Message(
        role="assistant",
        content="",
        tool_calls=[
            ToolCall(id="c1", name="read_file", arguments='{"path": "test.txt"}')
        ],
    )
    tokens_with_tools = meter.estimate_message(msg_with_tools)
    assert tokens_with_tools > tokens


def test_token_meter_accumulate_usage():
    """Test accumulating usage from TokenUsage objects and provider dicts."""
    meter = TokenMeter()

    meter.accumulate_usage(TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150))
    accum = meter.get_total_usage()
    assert accum.input_tokens == 100
    assert accum.output_tokens == 50
    assert accum.total_tokens == 150

    # Accumulate via standard OpenAI dict
    meter.accumulate_usage({
        "prompt_tokens": 200,
        "completion_tokens": 80,
        "cache_read_tokens": 50,
        "total_tokens": 280,
    })
    accum2 = meter.get_total_usage()
    assert accum2.input_tokens == 300
    assert accum2.output_tokens == 130
    assert accum2.cache_read_tokens == 50
    assert accum2.total_tokens == 430


# ==============================================================================
# Tier 2: OutputPruner
# ==============================================================================


def test_output_pruner_small_text_unmodified():
    """Test that text within threshold is preserved without modification."""
    pruner = OutputPruner(threshold_chars=500)
    text = "Short compiler log: Build successful."
    res, was_pruned, omitted = pruner.prune_text(text)

    assert not was_pruned
    assert omitted == 0
    assert res == text


def test_output_pruner_oversized_text():
    """Test middle omission truncation when text exceeds threshold."""
    pruner = OutputPruner(threshold_chars=200, head_chars=50, tail_chars=50)
    prefix = "HEAD_START_" + ("A" * 60)
    suffix = ("Z" * 60) + "_TAIL_END"
    middle = "M" * 500
    full_text = prefix + middle + suffix

    pruned_text, was_pruned, omitted = pruner.prune_text(full_text)

    assert was_pruned
    assert omitted == len(full_text) - 100
    assert pruned_text.startswith("HEAD_START_")
    assert pruned_text.endswith("_TAIL_END")
    assert f"[... {omitted} characters omitted ...]" in pruned_text


def test_output_pruner_head_tail_overflow_safe():
    """Test safe handling when head + tail >= text length."""
    pruner = OutputPruner(threshold_chars=10, head_chars=100, tail_chars=100)
    text = "medium length text"
    res, was_pruned, omitted = pruner.prune_text(text)

    assert not was_pruned
    assert res == text


# ==============================================================================
# Tier 3: CompactionEngine & 8-Section Structured Summarization
# ==============================================================================


def test_compaction_engine_8_section_summary():
    """Test generating a structured 8-section summary from historical messages."""
    engine = CompactionEngine()
    messages = [
        Message(role="user", content="Please build convex-lens simulation in physics_lab.py"),
        Message(role="assistant", content="Reading config file experiment.json"),
        Message(role="tool", content="Error: File not found: experiment.json"),
        Message(role="assistant", content="Fixing configuration error in physics_lab.py"),
    ]

    summary = engine.generate_8_section_summary(messages)

    # Must contain all eight standard sections
    for section in EIGHT_SECTIONS:
        assert section in summary

    # Must extract relevant files and errors
    assert "`experiment.json`" in summary or "experiment.json" in summary
    assert "convex-lens" in summary or "physics_lab.py" in summary


def test_compaction_two_stage_on_session(temp_workspace):
    """Test end-to-end context compaction on a live session."""
    session = Session(session_id="test_compaction_01", cwd=str(temp_workspace))
    compactor = CompactionEngine(
        pruner=OutputPruner(threshold_chars=100, head_chars=20, tail_chars=20)
    )

    # Append system message
    session.append("system/message", {"role": "system", "content": "You are a physics lab tutor."}, surface_op="append")

    # Append several turns of conversation
    for i in range(1, 6):
        session.append("user/message", {"role": "user", "content": f"Step {i}: Run optics experiment {i}."}, surface_op="append")
        session.append(
            "assistant/message",
            {"role": "assistant", "content": f"Processing step {i} with code."},
            surface_op="append",
        )
        # Giant tool output that triggers Stage 1 pruning
        session.append(
            "tool/result",
            {"role": "tool", "content": f"Tool output {i}: " + ("x" * 300)},
            surface_op="append",
        )

    # Active surface before compaction
    active_before = session.derive_messages()
    assert len(active_before) > 10

    # Trigger compaction with a low limit
    compacted = compactor.compact_if_needed(
        session,
        context_limit=100,  # Deliberately low to force compaction
        threshold_ratio=0.5,
        keep_recent_count=2,
    )

    assert compacted

    # Active surface after compaction
    active_after = session.derive_messages()

    # System message must remain at index 0
    assert active_after[0].role == "system"

    # There should now be a checkpoint message with PREAMBLE
    checkpoint_msgs = [m for m in active_after if CHECKPOINT_PREAMBLE in m.content]
    assert len(checkpoint_msgs) >= 1

    # Underlying session log is immutable: all original events remain
    assert len(session.log) >= 16
