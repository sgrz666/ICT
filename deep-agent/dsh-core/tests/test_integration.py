"""Integration test suite for dsh-core.

Tests cross-module synergy across file, sandbox, memory, and session subsystems:
1. End-to-end agent cycle: Read -> Execute -> Detect Bug -> Edit (Diff) -> Re-execute -> Pass.
2. Safe workspace containment during code mutation and execution.
3. Multi-turn dialogue with token budgeting, output pruning, and 8-section compaction.
4. Session state persistence and crash recovery round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsh_core.file import FileManager, StrReplaceEditor
from dsh_core.memory import (
    CHECKPOINT_PREAMBLE,
    EIGHT_SECTIONS,
    CompactionEngine,
    OutputPruner,
    TokenMeter,
)
from dsh_core.sandbox import ProcessSandbox, SandboxPolicy
from dsh_core.session import (
    SESSION_FORMAT_VERSION,
    JsonlPersistence,
    Message,
    Session,
    SessionEvent,
    SessionHeader,
    SurfaceOp,
)


def test_e2e_student_code_repair_cycle(temp_workspace: Path):
    """Scenario 1: Agent inspects buggy code, executes tests, repairs code, verifies pass."""
    # 1. Setup buggy student solution
    code_path = temp_workspace / "student_solver.py"
    code_path.write_text(
        "def solve(a, b):\n"
        "    # Bug: incorrect subtraction instead of addition\n"
        "    return a - b\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    assert solve(2, 3) == 5, f'Expected 5, got {solve(2, 3)}'\n"
        "    print('ALL_TESTS_PASSED')\n",
        encoding="utf-8",
    )

    file_mgr = FileManager(workspace_root=temp_workspace)
    sandbox = ProcessSandbox(
        workspace_root=temp_workspace,
        default_policy=SandboxPolicy.WORKSPACE_WRITE,
    )
    session = Session(session_id="sess_repair_01", cwd=str(temp_workspace))

    # Step 1: Agent starts turn and appends user message
    session.append(
        "user/message",
        {"role": "user", "content": "Please run student_solver.py and fix any failing assertions."},
        surface_op="append",
    )

    # Step 2: Sandbox executes the initial script -> should fail
    run1 = sandbox.execute("python student_solver.py", timeout=10)
    assert run1.exit_code != 0
    assert "AssertionError" in run1.stderr or "Expected 5" in run1.stderr

    # Step 3: File manager reads and performs exact string replacement with diff
    raw_code, _ = file_mgr.read_text("student_solver.py", with_line_numbers=False)
    assert "return a - b" in raw_code

    new_content, diff = file_mgr.edit_text(
        "student_solver.py",
        old_str="return a - b",
        new_str="return a + b",
    )
    assert "+    return a + b" in diff

    # Step 4: Re-run the script in sandbox -> must pass
    run2 = sandbox.execute("python student_solver.py", timeout=10)
    assert run2.exit_code == 0
    assert "ALL_TESTS_PASSED" in run2.stdout

    session.append(
        "tool/result",
        {"role": "tool", "content": run2.stdout},
        surface_op="append",
    )
    session.append(
        "assistant/message",
        {"role": "assistant", "content": "Fixed student_solver.py by changing subtraction to addition. Verified passing."},
        surface_op="append",
    )

    # Verify session recorded the actions cleanly
    messages = session.derive_messages()
    assert len(messages) == 3
    assert messages[0].content == "Please run student_solver.py and fix any failing assertions."
    assert "ALL_TESTS_PASSED" in messages[1].content


def test_e2e_experiment_parameter_modification(temp_workspace: Path):
    """Scenario 2: Modification of optics experiment configuration with atomic writes."""
    file_mgr = FileManager(workspace_root=temp_workspace)

    # Read optics config
    cfg_raw, _ = file_mgr.read_text("experiment_config.json", with_line_numbers=False)
    cfg = json.loads(cfg_raw)
    assert cfg["focal_length_mm"] == 50.0

    # Modify parameters
    cfg["focal_length_mm"] = 75.0
    cfg["rays_count"] = 1200
    new_cfg_raw = json.dumps(cfg, indent=2)

    file_mgr.write_text("experiment_config.json", new_cfg_raw)

    # Re-read and verify persistence
    verified_raw, _ = file_mgr.read_text("experiment_config.json", with_line_numbers=False)
    verified_cfg = json.loads(verified_raw)
    assert verified_cfg["focal_length_mm"] == 75.0
    assert verified_cfg["rays_count"] == 1200


def test_e2e_multi_turn_dialogue_with_compaction(temp_workspace: Path):
    """Scenario 3: 12-turn simulated tutoring session with token accumulation and 8-section compaction."""
    session = Session(session_id="sess_tutor_01", cwd=str(temp_workspace))
    compactor = CompactionEngine(
        pruner=OutputPruner(threshold_chars=80, head_chars=20, tail_chars=20)
    )

    session.append(
        "system/message",
        {"role": "system", "content": "You are a specialized physics lab tutor."},
        surface_op="append",
    )

    # Simulate 6 turns of tutoring conversation with verbose tool results
    for i in range(1, 7):
        session.append(
            "user/message",
            {"role": "user", "content": f"Turn {i}: Explain optical refraction concept #{i}."},
            surface_op="append",
        )
        session.append(
            "assistant/message",
            {"role": "assistant", "content": f"Running simulation for concept {i}."},
            surface_op="append",
        )
        session.append(
            "tool/result",
            {"role": "tool", "content": f"Raw ray tracer output {i}: " + ("ray_vector " * 50)},
            surface_op="append",
        )

    # Verify active messages before compaction
    pre_msgs = session.derive_messages()
    assert len(pre_msgs) == 1 + 6 * 3  # 1 system + 18 turn messages = 19

    # Trigger compaction
    compacted = compactor.compact_if_needed(
        session,
        context_limit=150,
        threshold_ratio=0.5,
        keep_recent_count=2,
    )
    assert compacted

    # Verify surface messages after compaction
    post_msgs = session.derive_messages()
    assert len(post_msgs) < len(pre_msgs)

    # System message must remain at index 0 (KV-cache prefix preservation)
    assert post_msgs[0].role == "system"

    # Checkpoint summary message exists
    checkpoint_msgs = [m for m in post_msgs if CHECKPOINT_PREAMBLE in (m.content or "")]
    assert len(checkpoint_msgs) >= 1
    chk = checkpoint_msgs[0].content

    # Check 8-section coverage in checkpoint
    for sec in EIGHT_SECTIONS:
        assert sec in chk


def test_e2e_persistence_crash_recovery(tmp_path: Path):
    """Scenario 4: Session writes to JSONL stream and can be restored intact after simulated crash."""
    storage_dir = tmp_path / "sessions_store"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    persistence = JsonlPersistence(
        storage_root=storage_dir,
        cwd=workspace_dir,
        session_id="recovery_test_01",
    )
    session = Session(session_id="recovery_test_01", cwd=str(workspace_dir), persistence=persistence)

    # Append turns
    session.append(
        "user/message",
        {"role": "user", "content": "Calculate focal length."},
        surface_op="append",
    )
    session.append(
        "assistant/message",
        {"role": "assistant", "content": "The focal length is f = 50mm."},
        surface_op="append",
    )
    session.append(
        "user/message",
        {"role": "user", "content": "What about magnification?"},
        surface_op="append",
    )
    session.append(
        "assistant/message",
        {"role": "assistant", "content": "Magnification m = -di / do."},
        surface_op="append",
    )

    # Verify persistence file exists and has records
    assert persistence.exists()
    header, events = persistence.load_session()
    assert header.id == "recovery_test_01"
    assert header.version == SESSION_FORMAT_VERSION
    assert len(events) == 4

    # Restore new session instance from persisted events
    restored_session = Session.restore(persistence)

    restored_msgs = restored_session.derive_messages()
    assert len(restored_msgs) == 4
    assert restored_msgs[0].content == "Calculate focal length."
    assert restored_msgs[3].content == "Magnification m = -di / do."
