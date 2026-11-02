"""Comprehensive test suite for all advanced DeepSeek Harness subsystems in dsh-core.

Tests:
1. FsObservationPolicy (`FS_NOT_OBSERVED`, `FS_STALE`, `createIfAbsent`, `replaceIfVersion`)
2. BackgroundJobManager (`start_job`, `list_jobs`, `get_job_output`, `kill_job`)
3. SpillStore & SpillPolicy (disk spill retention before middle truncation) & ImageOffloadPolicy
4. SessionProjectionRegistry (`sessionStats`, `turnOutline`, `turnBoundary`) & SessionQueryService
5. RepeatToolReminder (key-order canonicalization, gentle @ 3, detailed @ 5) & ToolTimeoutPolicy
6. TodoManager, PlanModeManager (mutating tool block + `# ` exit approval), GoalManager & GoalRoundDriver (`MIN_ROUNDS_BEFORE_BLOCK = 3`, CAS revision)
7. SkillRegistry & FilesystemSkillProvider, InstructionLoader (`AGENTS.md`), FileReferenceResolver (`@file`), SystemPromptBuilder (`in_history` KV-cache preservation)
8. SubagentManager (`spawn` vs `fork` with `completed_turn_prefix`, `send_message`, `interrupt_agent`, `max_depth`)
9. ApprovalManager, UserQuestionManager, DeliverableManager, WorkspaceChangeTracker
10. LabKitBridge (all 6 `experiment_*` tools across mechanics, pendulum, circuits, optics)
11. AgentLoop & AgentPresetRegistry (`standard`, `physics-lab`, `plan`, `minimal`) end-to-end execution and `run_with_goal_driver`
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from dsh_core import (
    GENTLE_REMINDER,
    MIN_ROUNDS_BEFORE_BLOCK,
    AgentLoop,
    AgentPresetRegistry,
    ApprovalDeniedError,
    ApprovalManager,
    BackgroundJobManager,
    DeliverableManager,
    FileManager,
    FileReferenceResolver,
    FilesystemSkillProvider,
    FsNotObservedError,
    FsStaleFileError,
    GoalError,
    GoalManager,
    GoalRoundDriver,
    ImageOffloadPolicy,
    InstructionLoader,
    JobStatus,
    LabKitBridge,
    Message,
    MockLlmClient,
    PlanModeManager,
    PlanModeViolationError,
    RepeatToolReminder,
    Role,
    Session,
    SessionProjectionRegistry,
    SessionQueryService,
    SkillRegistry,
    SpillPolicy,
    SpillStore,
    SubagentManager,
    SystemPromptBuilder,
    TodoManager,
    TodoValidationError,
    ToolCall,
    ToolCallTimeoutError,
    ToolTimeoutPolicy,
    UserQuestionManager,
    WorkspaceChangeTracker,
    canonicalize_arguments,
    completed_turn_prefix,
)


# ── 1. FsObservationPolicy Tests ──────────────────────────────────────────────
def test_fs_observation_policy_read_before_edit_and_write(tmp_path: Path) -> None:
    fm = FileManager(workspace_root=tmp_path, enforce_observation=True)

    # Creating a brand-new file that does not yet exist is allowed (`createIfAbsent`)
    fm.write_text("new_script.py", "x = 1\n")
    assert (tmp_path / "new_script.py").read_text(encoding="utf-8") == "x = 1\n"

    # Externally created file that the agent has NEVER read
    unseen = tmp_path / "existing.py"
    unseen.write_text("value = 10\n", encoding="utf-8")

    # Attempting to edit or overwrite `existing.py` without reading first raises FsNotObservedError
    with pytest.raises(FsNotObservedError, match="FS_NOT_OBSERVED"):
        fm.edit_text("existing.py", "value = 10", "value = 20")

    with pytest.raises(FsNotObservedError, match="FS_NOT_OBSERVED"):
        fm.write_text("existing.py", "value = 99\n")

    # Reading the file records its observation version
    content, _ = fm.read_text("existing.py")
    assert "value = 10" in content

    # External modification after read triggers FsStaleFileError (`FS_STALE`)
    unseen.write_text("value = 777\n", encoding="utf-8")
    with pytest.raises(FsStaleFileError, match="FS_STALE"):
        fm.edit_text("existing.py", "value = 10", "value = 20")

    # Re-reading refreshes observation and allows clean edit
    fm.read_text("existing.py")
    _, diff = fm.edit_text("existing.py", "value = 777", "value = 888")
    assert "+value = 888" in diff


# ── 2. BackgroundJobManager Tests ─────────────────────────────────────────────
def test_background_job_manager_lifecycle(tmp_path: Path) -> None:
    jm = BackgroundJobManager(workspace_root=tmp_path)
    py_exe = f'"{sys.executable}"'

    # Start a short background job that prints output and exits 0
    job1 = jm.start_job(
        f'{py_exe} -c "import time; print(\'hello_bg_job\', flush=True); time.sleep(0.1)"',
        owner_session_id="sess_a",
    )
    assert job1.owner_session_id == "sess_a"
    assert len(jm.list_jobs(owner_session_id="sess_a")) == 1
    assert len(jm.list_jobs(owner_session_id="sess_b")) == 0

    snap1 = jm.get_job_output(job1.job_id, wait_timeout=3.0)
    assert snap1.status == JobStatus.COMPLETED
    assert snap1.exit_code == 0
    assert "hello_bg_job" in snap1.stdout

    # Start a long-running job and kill it via `kill_job`
    job2 = jm.start_job(
        f'{py_exe} -c "import time; time.sleep(10)"',
        owner_session_id="sess_a",
    )
    killed_summary = jm.kill_job(job2.job_id)
    assert killed_summary.status == JobStatus.KILLED


# ── 3. SpillStore, SpillPolicy & ImageOffloadPolicy Tests ─────────────────────
def test_spill_policy_persists_full_output_to_disk(tmp_path: Path) -> None:
    store = SpillStore(spill_root=tmp_path / "spills")
    policy = SpillPolicy(spill_store=store, max_inline_tokens=120)

    # Small text within budget is not spilled
    small, ref_none = policy.bound_tool_result("short output", "s1", "read_file", "c1")
    assert small == "short output"
    assert ref_none is None

    # Large text exceeding 120 tokens (~480 chars) is spilled to disk first
    large_text = "\n".join(f"line_{i:04d}: data_payload_value={i * 10}" for i in range(100))
    bounded, ref = policy.bound_tool_result(large_text, "s1", "grep_search", "call_99")
    assert ref is not None
    assert Path(ref.path).is_file()
    assert Path(ref.path).read_text(encoding="utf-8") == large_text
    assert "[Spill Notice:" in bounded
    assert "line_0000" in bounded
    assert "990" in bounded


def test_image_offload_policy() -> None:
    session = Session(session_id="img_sess")
    policy = ImageOffloadPolicy(max_active_images=2)

    for idx in range(4):
        session.append(
            "user/message",
            {
                "role": "user",
                "content": f"Diagram {idx} [Image: fig_{idx}.png]",
                "has_image": True,
                "image_id": f"fig_{idx}.png",
            },
            surface_op="append",
        )

    offloaded = policy.offload_if_needed(session)
    assert offloaded == 2
    assert session.log[0].data.get("image_offloaded") is True
    assert session.log[1].data.get("image_offloaded") is True
    assert session.log[2].data.get("has_image") is True
    assert session.log[3].data.get("has_image") is True
    assert session.log[-1].type == "image/offload"


# ── 4. SessionProjectionRegistry & SessionQueryService Tests ──────────────────
def test_session_projections_and_query_service() -> None:
    session = Session(session_id="proj_sess", cwd="/workspace")
    reg = SessionProjectionRegistry(register_defaults=True)

    session.append("turn/start", {"turn": 1})
    session.append("user/message", {"role": "user", "content": "Measure pendulum period T"}, surface_op="append")
    session.append("step/start", {"turn": 1, "step": 1})
    session.append(
        "assistant/message",
        {
            "role": "assistant",
            "content": "Calling simulate",
            "tool_calls": [{"id": "tc1", "function": {"name": "experiment_simulate", "arguments": "{}"}}],
        },
        surface_op="append",
    )
    session.append("tool/result", {"role": "tool", "tool_call_id": "tc1", "content": "T=2.006s"}, surface_op="append")
    session.append("step/end", {"turn": 1, "step": 1})
    session.append("turn/end", {"turn": 1, "reason": "complete"})

    stats = reg.state_of(session, "sessionStats")
    assert stats.turns == 1
    assert stats.steps == 1
    assert stats.user_messages == 1
    assert stats.assistant_messages == 1
    assert stats.tool_calls == 1
    assert stats.tool_results == 1

    outline = reg.state_of(session, "turnOutline")
    assert len(outline) == 1
    assert outline[0].turn == 1
    assert outline[0].user_preview == "Measure pendulum period T"
    assert outline[0].tool_names == ["experiment_simulate"]
    assert outline[0].end_seq is not None

    boundary = reg.state_of(session, "turnBoundary")
    assert boundary.current_turn == 1
    assert boundary.in_turn is False

    # Query service search & markdown export
    matches = SessionQueryService.search_events(session, "pendulum")
    assert len(matches) == 1
    md = SessionQueryService.export_markdown(session)
    assert "# Session Transcript: `proj_sess`" in md
    assert "Measure pendulum period T" in md


# ── 5. RepeatToolReminder & ToolTimeoutPolicy Tests ───────────────────────────
def test_repeat_tool_reminder_canonicalization_and_thresholds() -> None:
    assert canonicalize_arguments({"b": 2, "a": [1, {"z": 9, "y": 8}]}) == canonicalize_arguments(
        {"a": [1, {"y": 8, "z": 9}], "b": 2}
    )

    guard = RepeatToolReminder(thresholds=(3, 5))
    assert guard.record_call("read_file", {"path": "a.py", "offset": 1}) is None
    assert guard.record_call("read_file", {"offset": 1, "path": "a.py"}) is None
    # 3rd identical call triggers gentle reminder
    rem3 = guard.record_call("read_file", {"path": "a.py", "offset": 1})
    assert rem3 == GENTLE_REMINDER
    # 4th call (between thresholds) returns None
    assert guard.record_call("read_file", {"path": "a.py", "offset": 1}) is None
    # 5th call triggers detailed reminder
    rem5 = guard.record_call("read_file", {"path": "a.py", "offset": 1})
    assert rem5 is not None and "consecutive_calls: 5" in rem5

    # Calling with different arguments resets streak
    assert guard.record_call("read_file", {"path": "b.py", "offset": 1}) is None
    assert guard.get_streak() == 1


def test_tool_timeout_policy_enforces_deadline() -> None:
    policy = ToolTimeoutPolicy(default_timeout_seconds=0.2, per_tool_timeouts={"slow_tool": 0.15})

    def _fast(args: dict[str, int]) -> int:
        return args["x"] + 1

    def _slow(_args: dict[str, int]) -> int:
        time.sleep(1.0)
        return 42

    assert policy.execute_with_timeout("fast_tool", _fast, {"x": 5}) == 6
    with pytest.raises(ToolCallTimeoutError, match="timed out"):
        policy.execute_with_timeout("slow_tool", _slow, {})


# ── 6. Autonomy: Todo, PlanMode, Goal & GoalRoundDriver Tests ─────────────────
def test_todo_manager_validation_and_projections() -> None:
    session = Session(session_id="todo_sess")
    proj = SessionProjectionRegistry()
    tm = TodoManager(projection_registry=proj)

    items = tm.write_todos(
        session,
        [
            {"content": "Inspect optics template", "status": "completed"},
            {"content": "Run L2 simulation", "status": "in_progress"},
            {"content": "Verify HTML CSP", "status": "pending"},
        ],
    )
    assert len(items) == 3
    assert len(proj.state_of(session, "todos")) == 3

    # Duplicate content raises TodoValidationError
    with pytest.raises(TodoValidationError, match="duplicate"):
        tm.write_todos(
            session,
            [
                {"content": "Same task", "status": "pending"},
                {"content": "Same task", "status": "in_progress"},
            ],
        )


def test_plan_mode_blocks_mutations_until_approved_exit() -> None:
    session = Session(session_id="plan_sess")
    pm = PlanModeManager()
    pm.enter_plan_mode(session)
    assert pm.is_active(session.session_id) is True
    assert pm.get_system_prompt_section(session.session_id) is not None

    # Mutating tools are blocked while in plan mode
    with pytest.raises(PlanModeViolationError, match="forbidden while in plan mode"):
        pm.check_tool_allowed(session.session_id, "write_file")

    # Read-only tools are permitted
    pm.check_tool_allowed(session.session_id, "read_file")

    # Submitting a plan without `#` heading fails validation
    with pytest.raises(ValueError, match="Markdown `#` heading"):
        pm.exit_plan_mode(session, "Invalid plan without heading")

    res = pm.exit_plan_mode(session, "# Implementation Plan\n1. Step one\n2. Step two")
    assert res.approved is True
    assert res.exited_plan_mode is True
    assert pm.is_active(session.session_id) is False
    # Now write_file is allowed
    pm.check_tool_allowed(session.session_id, "write_file")


def test_goal_manager_and_round_driver_enforces_3_round_block_floor() -> None:
    session = Session(session_id="goal_sess")
    gm = GoalManager()
    driver = GoalRoundDriver(goal_manager=gm)

    view = gm.create_goal(session, objective="Deliver complete Ohm's law package", max_goal_rounds=5)
    assert view.goal.phase == "active"
    assert view.rounds_started == 0

    # Official rule: cannot mark `blocked` before MIN_ROUNDS_BEFORE_BLOCK (3) rounds
    with pytest.raises(GoalError, match=f"before {MIN_ROUNDS_BEFORE_BLOCK} rounds"):
        gm.update_goal(
            session,
            phase="blocked",
            blocked_reason={"code": "missing_dep", "message": "Need library"},
        )

    # Advance 3 rounds via GoalRoundDriver
    for expected_round in (1, 2, 3):
        assert driver.is_drivable(session) is True
        prompt = driver.advance_round(session)
        assert prompt is not None
        assert f"[GOAL ROUND {expected_round}/5]" in prompt

    # After 3 rounds, transitioning to `blocked` with a reason succeeds
    blocked_view = gm.update_goal(
        session,
        phase="blocked",
        blocked_reason={"code": "env_limit", "message": "External hardware absent"},
    )
    assert blocked_view.goal.phase == "blocked"
    assert blocked_view.activation == "disarmed"
    assert driver.is_drivable(session) is False


# ── 7. Skill, Instructions, @file Reference & SystemPromptBuilder Tests ───────
def test_skill_registry_instructions_and_file_references(tmp_path: Path) -> None:
    # Create AGENTS.md and a sample file in workspace
    (tmp_path / "AGENTS.md").write_text("# Workspace Rule\nAlways sync README.md.", encoding="utf-8")
    (tmp_path / "circuit.py").write_text("V = 5.0\nR = 100.0\nI = V / R\n", encoding="utf-8")

    # Create a SKILL.md inside skills/physics-helper/SKILL.md
    skill_dir = tmp_path / "skills" / "physics-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: physics-helper\ndescription: Validates SI units and significant figures.\n---\nUse MKS units.",
        encoding="utf-8",
    )

    reg = SkillRegistry()
    reg.load_from_provider(FilesystemSkillProvider([skill_dir.parent]))
    skills = reg.list_skills()
    assert len(skills) == 1
    assert skills[0].name == "physics-helper"
    assert "Use MKS units." in reg.get_skill("physics-helper").body

    loader = InstructionLoader(workspace_root=tmp_path)
    instr = loader.load_instructions()
    assert "Always sync README.md" in instr

    fm = FileManager(workspace_root=tmp_path)
    resolver = FileReferenceResolver(file_manager=fm)
    expanded = resolver.resolve_prompt_references("Please check @circuit.py for Ohm's law")
    assert '<file_reference path="circuit.py"' in expanded
    assert "I = V / R" in expanded

    # SystemPromptBuilder KV-cache friendly in_history update
    session = Session(session_id="sp_sess")
    builder = SystemPromptBuilder(persona_prefix="Base Persona")
    builder.set_section("instructions", instr, priority=20)
    builder.apply_to_session(session, in_history_update=True)
    assert len(session.log) == 1

    # Updating section appends an `in_history=True` system message rather than mutating seq 0
    builder.set_section("skills", reg.format_catalog_section(), priority=30)
    builder.apply_to_session(session, in_history_update=True)
    assert len(session.log) == 2
    assert session.log[1].data.get("in_history") is True


# ── 8. SubagentManager (`spawn` vs `fork` with KV-cache prefix) Tests ─────────
def test_subagent_spawn_vs_fork_completed_turn_prefix() -> None:
    parent = Session(session_id="parent_01", cwd="/workspace")
    parent.append("turn/start", {"turn": 1})
    parent.append("user/message", {"role": "user", "content": "Context from turn 1"}, surface_op="append")
    parent.append("assistant/message", {"role": "assistant", "content": "Ack turn 1"}, surface_op="append")
    parent.append("turn/end", {"turn": 1, "reason": "complete"})

    # Start an unfinished in-flight turn 2
    parent.append("turn/start", {"turn": 2})
    parent.append("user/message", {"role": "user", "content": "Unfinished turn 2"}, surface_op="append")

    prefix = completed_turn_prefix(parent)
    assert len(prefix) == 4
    assert prefix[-1].type == "turn/end"

    mgr = SubagentManager(max_depth=2)
    spawn_sum = mgr.spawn(parent, role="Researcher", prompt="Find lens formula")
    assert spawn_sum.mode == "spawn"
    assert spawn_sum.seed_length == 0

    fork_sum = mgr.fork(parent, role="Verifier", prompt="Verify turn 1 equations")
    assert fork_sum.mode == "fork"
    assert fork_sum.seed_length == 4
    fork_record = mgr.get_record(fork_sum.agent_id)
    # Child session has the 4 inherited prefix events + 6 new turn events
    assert len(fork_record.session.log) == 10

    # Follow-up message and interrupt
    updated = mgr.send_message(fork_sum.agent_id, "Double check focal length")
    assert updated.status == "completed"
    interrupted = mgr.interrupt_agent(fork_sum.agent_id)
    assert interrupted.status == "interrupted"


# ── 9. Interaction: Approval, Questions, Deliverables & WorkspaceChanges ──────
def test_interaction_approval_questions_deliverables_and_changes(tmp_path: Path) -> None:
    session = Session(session_id="inter_sess", cwd=str(tmp_path))

    # ApprovalManager in read-only mode blocks write_file
    am = ApprovalManager(preset="read-only")
    with pytest.raises(ApprovalDeniedError):
        am.check_approval("write_file", {"path": "a.txt", "content": "hi"})

    # UserQuestionManager (headless default picks first option)
    qm = UserQuestionManager()
    q_resp = qm.ask(session, "Which lens?", options=["Convex f=10cm", "Concave f=-10cm"])
    assert q_resp.selected_options == ["Convex f=10cm"]

    # WorkspaceChangeTracker & DeliverableManager
    tracker = WorkspaceChangeTracker(workspace_root=tmp_path)
    tracker.begin_turn()
    report_file = tmp_path / "experiment_report.md"
    report_file.write_text("# Lens Report\nVerified.", encoding="utf-8")
    changes = tracker.end_turn(session, turn=1)
    assert changes.created == ["experiment_report.md"]

    dm = DeliverableManager(workspace_root=tmp_path)
    item = dm.present(session, path="experiment_report.md", title="Convex Lens Report")
    assert item.path == "experiment_report.md"
    assert item.size_bytes > 0


# ── 10. LabKitBridge Physics & Circuit 6-Tool Pipeline Tests ──────────────────
def test_labkit_bridge_all_four_domains_and_5_file_build(tmp_path: Path) -> None:
    bridge = LabKitBridge(output_root=tmp_path / "labkit_out")

    recipes_res = bridge.experiment_recipes()
    assert recipes_res["count"] == 9

    for recipe_id in (
        "oblique45",
        "period-length",
        "ohms-law",
        "convex-lens",
    ):
        val = bridge.experiment_validate(recipe_id=recipe_id)
        assert val["ok"] is True

        sim = bridge.experiment_simulate(recipe_id=recipe_id)
        assert sim["ok"] is True
        assert sim["max_error_pct"] <= sim["tolerance_pct"]

    # Full 5-file build for Ohm's law
    pkg = bridge.experiment_build(
        recipe_id="ohms-law",
        params={"voltage_v": 6.0, "resistance_ohm": 120.0},
        why_recipe="Demonstrate I=U/R linear relationship",
        student_task="Plot I vs U and compute slope 1/R",
        out_name="ohms_law_test_pkg",
    )
    assert pkg["ok"] is True
    for key in ("html", "evidence", "teacher_guide", "student_worksheet", "package_manifest"):
        assert Path(pkg["files"][key]).is_file()


# ── 11. AgentLoop & AgentPresetRegistry End-to-End Execution Tests ────────────
def test_agent_loop_end_to_end_physics_lab_and_goal_driver(tmp_path: Path) -> None:
    preset_reg = AgentPresetRegistry()
    assert set(preset_reg.list_ids()) == {"standard", "physics-lab", "plan", "minimal"}

    llm = MockLlmClient()
    # Turn 1 Step 1: Agent creates a goal, writes a todo, and builds a pendulum experiment package
    llm.queue_response(
        Message(
            role="assistant",
            content="Initializing goal and building pendulum experiment package.",
            tool_calls=[
                ToolCall(
                    id="call_goal_1",
                    name="create_goal",
                    arguments=json.dumps({"objective": "Build pendulum package and complete goal", "max_goal_rounds": 4}),
                ),
                ToolCall(
                    id="call_todo_1",
                    name="todo_write",
                    arguments=json.dumps(
                        {"todos": [{"content": "Build pendulum experiment", "status": "in_progress"}]}
                    ),
                ),
                ToolCall(
                    id="call_exp_1",
                    name="experiment_build",
                    arguments=json.dumps(
                        {
                            "recipe_id": "period-length",
                            "out_name": "pendulum_iso",
                        }
                    ),
                ),
            ],
        )
    )
    # Turn 1 Step 2: Agent finishes Turn 1 without marking goal complete yet (so GoalRoundDriver triggers Turn 2)
    llm.queue_response(
        Message(
            role="assistant",
            content="Pendulum package built; awaiting goal verification round.",
        )
    )
    # Turn 2 Step 1 (driven automatically by GoalRoundDriver): Agent marks todo and goal complete
    llm.queue_response(
        Message(
            role="assistant",
            content="Verifying artifacts and completing goal.",
            tool_calls=[
                ToolCall(
                    id="call_todo_2",
                    name="todo_write",
                    arguments=json.dumps(
                        {"todos": [{"content": "Build pendulum experiment", "status": "completed"}]}
                    ),
                ),
                ToolCall(
                    id="call_goal_2",
                    name="update_goal",
                    arguments=json.dumps({"phase": "complete"}),
                ),
            ],
        )
    )
    # Turn 2 Step 2: Final response
    llm.queue_response(
        Message(
            role="assistant",
            content="Goal completed and verified!",
        )
    )

    loop = AgentLoop(workspace_root=tmp_path, llm_client=llm, preset_id="standard")
    summaries = loop.run_with_goal_driver("Please build the pendulum isochronism experiment.")

    assert len(summaries) == 2
    assert "experiment_build" in summaries[0].tool_calls_made
    assert "update_goal" in summaries[1].tool_calls_made
    assert summaries[1].final_assistant_text == "Goal completed and verified!"

    # Verify that the 5 experiment files were created on disk and tracked in workspace_changes
    assert summaries[0].workspace_changes is not None
    assert summaries[0].workspace_changes.has_changes is True
    goal_view = loop.goal_manager.get_goal(loop.session)
    assert goal_view is not None
    assert goal_view.goal.phase == "complete"
