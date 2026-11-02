"""Tests for the dsh-core session subsystem.

Covers:
- SurfaceManager (event filtering, node appending, range replacement)
- JsonlPersistence (project key sanitization, session id encoding, atomic JSONL writes, load_session)
- Session event appending and model message derivation
- ReactLoopInbox & ReactLoopState turn/step state machine transitions
- End-to-end session persistence and round-trip restoration
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsh_core.session import (
    SESSION_FORMAT_VERSION,
    JsonlPersistence,
    Message,
    MockLlmClient,
    ReactLoopInbox,
    ReactLoopState,
    Session,
    SessionEvent,
    SessionHeader,
    SurfaceManager,
    SurfaceOp,
    ToolCall,
    ToolResult,
    Turn,
    encode_session_id,
    project_key,
)


# ==============================================================================
# Tier 1: SurfaceManager
# ==============================================================================


def test_surface_manager_append_and_filter():
    """Test that SurfaceManager appends eligible events and ignores non-surface events."""
    mgr = SurfaceManager()

    # Surface eligible event
    user_event = SessionEvent(
        seq=0,
        type="user/message",
        data={"role": "user", "content": "Hello"},
        surface_op=SurfaceOp(op="append"),
    )
    mgr.apply(user_event)
    assert mgr.get_active_seqs() == [0]

    # Non-surface event (e.g. step/start)
    step_event = SessionEvent(seq=1, type="step/start", data={"step": 1})
    mgr.apply(step_event)
    # Still [0]
    assert mgr.get_active_seqs() == [0]

    # Another eligible event
    asst_event = SessionEvent(
        seq=2,
        type="assistant/message",
        data={"role": "assistant", "content": "Hi there"},
        surface_op=SurfaceOp(op="append"),
    )
    mgr.apply(asst_event)
    assert mgr.get_active_seqs() == [0, 2]


def test_surface_manager_range_replacement():
    """Test replacing a slice of active sequence numbers (context compaction)."""
    mgr = SurfaceManager(initial_nodes=[0, 1, 2, 3, 4, 5])

    # Replace sequence range [1, 4] with checkpoint event 10
    replace_event = SessionEvent(
        seq=10,
        type="user/message",
        data={"role": "user", "content": "[CHECKPOINT]"},
        surface_op=SurfaceOp(op="replace", start_seq=1, end_seq=4),
    )
    mgr.apply(replace_event)

    # Expected: 0 is kept, 1..4 replaced by 10, 5 is kept -> [0, 10, 5]
    assert mgr.get_active_seqs() == [0, 10, 5]


# ==============================================================================
# Tier 2: JsonlPersistence & Path Sanitization
# ==============================================================================


def test_path_sanitization_helpers():
    """Test project_key and encode_session_id helper functions."""
    key = project_key(r"D:\codeplus\ICT")
    assert key.startswith("--") and key.endswith("--")
    assert "codeplus" in key
    assert ":" not in key

    s_id = encode_session_id("my/session:id*123")
    assert "/" not in s_id and ":" not in s_id and "*" not in s_id
    assert s_id == "my_session_id_123"


def test_jsonl_persistence_io(tmp_path: Path):
    """Test initializing, appending, and loading from JSONL file."""
    persistence = JsonlPersistence(
        storage_root=tmp_path / "storage",
        cwd=tmp_path / "workspace",
        session_id="test_session_001",
    )

    assert not persistence.exists()

    header = SessionHeader(id="test_session_001", cwd=str(tmp_path / "workspace"))
    file_path = persistence.init_session(header)

    assert persistence.exists()
    assert file_path.is_file()

    # Append 2 events
    ev1 = SessionEvent(seq=0, type="turn/start", data={"turn": 1})
    ev2 = SessionEvent(
        seq=1,
        type="user/message",
        data={"role": "user", "content": "Ping"},
        surface_op=SurfaceOp(op="append"),
    )
    persistence.append_event(ev1)
    persistence.append_event(ev2)

    # Load back
    loaded_header, loaded_events = persistence.load_session()
    assert loaded_header.id == "test_session_001"
    assert loaded_header.version == SESSION_FORMAT_VERSION
    assert len(loaded_events) == 2
    assert loaded_events[0].type == "turn/start"
    assert loaded_events[1].data["content"] == "Ping"


# ==============================================================================
# Tier 3: Session State Machine & React Loop
# ==============================================================================


def test_session_append_and_derive_messages(temp_workspace: Path):
    """Test session appending events and extracting OpenAI-compatible messages."""
    session = Session(session_id="sess_derive_01", cwd=str(temp_workspace))

    session.append(
        "system/message",
        {"role": "system", "content": "System prompt instructions."},
        surface_op="append",
    )
    session.append(
        "user/message",
        {"role": "user", "content": "Adjust focal length to 60mm."},
        surface_op="append",
    )
    session.append(
        "assistant/message",
        {
            "role": "assistant",
            "content": "Calling tool to inspect config.",
            "tool_calls": [
                {
                    "id": "c_inspect",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "config.json"}'},
                }
            ],
        },
        surface_op="append",
    )
    session.append(
        "tool/result",
        {
            "call_id": "c_inspect",
            "name": "read_file",
            "output": '{"focal_length": 50.0}',
        },
        surface_op="append",
    )

    messages = session.derive_messages()
    assert len(messages) == 4
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert messages[2].role == "assistant"
    assert messages[2].tool_calls is not None
    assert messages[2].tool_calls[0].name == "read_file"
    assert messages[3].role == "tool"
    assert messages[3].tool_call_id == "c_inspect"


def test_session_round_trip_restore(tmp_path: Path):
    """Test full round-trip: creating session with persistence and restoring it."""
    storage_root = tmp_path / "sessions_store"
    workspace_root = tmp_path / "agent_ws"
    workspace_root.mkdir(parents=True, exist_ok=True)

    pers = JsonlPersistence(storage_root, workspace_root, "restore_test_sess")
    session1 = Session(session_id="restore_test_sess", cwd=str(workspace_root), persistence=pers)

    session1.append("user/message", {"role": "user", "content": "Initial query"}, surface_op="append")
    session1.append("assistant/message", {"role": "assistant", "content": "Initial reply"}, surface_op="append")

    # Restore in new session instance
    session2 = Session.restore(pers)

    assert session2.id == "restore_test_sess"
    assert len(session2.log) == 2
    assert session2.surface_manager.get_active_seqs() == [0, 1]

    msgs = session2.derive_messages()
    assert len(msgs) == 2
    assert msgs[0].content == "Initial query"
    assert msgs[1].content == "Initial reply"


def test_react_loop_inbox_and_transitions(temp_workspace: Path):
    """Test ReactLoopInbox queue handling and ReactLoopState phase changes."""
    session = Session(session_id="react_test_01", cwd=str(temp_workspace))
    inbox = ReactLoopInbox()
    loop = ReactLoopState(session=session, inbox=inbox)

    assert loop.phase == "idle"
    assert not inbox.has_pending()

    # Enqueue user message
    inbox.push_user_message("Create concave lens experiment")
    assert inbox.has_pending()

    # Start turn
    turn = loop.start_turn()
    assert turn.turn_number == 1
    assert loop.phase == "running"

    # Start step
    step = loop.start_step()
    assert step.step_number == 1

    # End step and turn
    loop.end_step()
    loop.end_turn(reason="completed")
    assert loop.phase == "idle"

    # Session log has recorded lifecycle events
    event_types = [e.type for e in session.log]
    assert "turn/start" in event_types
    assert "step/start" in event_types
    assert "step/end" in event_types
    assert "turn/end" in event_types
