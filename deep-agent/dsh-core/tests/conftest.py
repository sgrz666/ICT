"""Pytest configuration and shared fixtures for dsh-core test suite.

Provides isolated ephemeral workspaces, mock LLM clients, sample session events,
and configured subsystem managers across all 4 verification tiers.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Generator

import pytest

# Ensure dsh_core package in src/ is discoverable
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create and initialize an isolated temporary workspace directory."""
    workspace = tmp_path / "agent_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Populate with baseline sample files
    (workspace / "hello.txt").write_text(
        "Line 1: Alpha\nLine 2: Beta\nLine 3: Gamma\nLine 4: Delta\nLine 5: Epsilon\n",
        encoding="utf-8",
    )

    (workspace / "sample_code.py").write_text(
        "def calculate_area(width, height):\n    return width * height\n\nif __name__ == '__main__':\n    print(f'Area: {calculate_area(5, 10)}')\n",
        encoding="utf-8",
    )

    (workspace / "experiment_config.json").write_text(
        json.dumps(
            {
                "experiment_id": "optics-convex-lens-01",
                "focal_length_mm": 50.0,
                "object_distance_mm": 100.0,
                "lens_refractive_index": 1.5,
                "aperture_diameter_mm": 25.0,
                "rays_count": 500,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    sub_dir = workspace / "src_sub"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / "nested.txt").write_text("Nested content line.\n", encoding="utf-8")

    return workspace


@pytest.fixture
def file_manager(temp_workspace: Path):
    """Provide a configured FileManager bound to the temporary workspace."""
    from dsh_core.file import FileManager

    return FileManager(workspace_root=temp_workspace, enforce_containment=True)


@pytest.fixture
def sample_session_events() -> list[dict[str, Any]]:
    """Generate a sequence of standard Version 4 session events."""
    base_time = 1730000000.0
    return [
        {
            "seq": 0,
            "time": base_time,
            "type": "turn/start",
            "data": {"turn": 1},
        },
        {
            "seq": 1,
            "time": base_time + 0.1,
            "type": "step/start",
            "data": {"turn": 1, "step": 1},
        },
        {
            "seq": 2,
            "time": base_time + 0.2,
            "type": "user/message",
            "data": {
                "role": "user",
                "content": "Please inspect experiment_config.json and change focal_length_mm to 60.0.",
            },
            "surface_op": "append",
        },
        {
            "seq": 3,
            "time": base_time + 0.5,
            "type": "assistant/message",
            "data": {
                "role": "assistant",
                "content": "I will read the configuration file first.",
                "tool_calls": [
                    {
                        "id": "call_read_01",
                        "type": "function",
                        "name": "read_file",
                        "arguments": json.dumps({"path": "experiment_config.json"}),
                    }
                ],
            },
            "surface_op": "append",
        },
        {
            "seq": 4,
            "time": base_time + 0.6,
            "type": "tool/call",
            "data": {
                "turn": 1,
                "step": 1,
                "call_id": "call_read_01",
                "name": "read_file",
                "arguments": json.dumps({"path": "experiment_config.json"}),
            },
        },
        {
            "seq": 5,
            "time": base_time + 0.7,
            "type": "tool/result",
            "data": {
                "turn": 1,
                "step": 1,
                "call_id": "call_read_01",
                "output": "1: {\n2:   \"experiment_id\": \"optics-convex-lens-01\",\n3:   \"focal_length_mm\": 50.0\n4: }",
            },
            "surface_op": "append",
            "source_event_seqs": [4],
        },
        {
            "seq": 6,
            "time": base_time + 0.8,
            "type": "step/end",
            "data": {"turn": 1, "step": 1},
        },
        {
            "seq": 7,
            "time": base_time + 0.9,
            "type": "turn/end",
            "data": {"turn": 1, "reason": "completed"},
        },
    ]
