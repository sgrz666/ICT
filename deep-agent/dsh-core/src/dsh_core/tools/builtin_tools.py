"""Built-in model-facing tool suite for dsh-core.

Registers the full DeepSeek Harness + EduForge LabKit tool catalog onto a
`ToolRegistry` instance, covering filesystem, search, shell/sandbox, background
jobs, todo/plan/goal autonomy, skills, subagents, user questions, deliverables,
session query, and physics/circuit experiments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .registry import ToolDefinition, ToolRegistry

if TYPE_CHECKING:
    from ..autonomy.goal import GoalManager
    from ..autonomy.plan_mode import PlanModeManager
    from ..autonomy.todo import TodoManager
    from ..file.manager import FileManager
    from ..file.search import WorkspaceSearcher
    from ..interaction.deliverables import DeliverableManager
    from ..interaction.questions import UserQuestionManager
    from ..labkit.bridge import LabKitBridge
    from ..sandbox.jobs import BackgroundJobManager
    from ..sandbox.process_runner import ProcessSandbox
    from ..session.projection import SessionQueryService
    from ..session.state_machine import Session
    from ..skill.skill_registry import SkillRegistry
    from ..subagent.manager import SubagentManager


def register_builtin_tools(
    registry: ToolRegistry,
    session: Session,
    file_manager: FileManager,
    searcher: WorkspaceSearcher | None = None,
    sandbox: ProcessSandbox | None = None,
    job_manager: BackgroundJobManager | None = None,
    todo_manager: TodoManager | None = None,
    plan_manager: PlanModeManager | None = None,
    goal_manager: GoalManager | None = None,
    skill_registry: SkillRegistry | None = None,
    subagent_manager: SubagentManager | None = None,
    question_manager: UserQuestionManager | None = None,
    deliverable_manager: DeliverableManager | None = None,
    query_service: SessionQueryService | None = None,
    labkit_bridge: LabKitBridge | None = None,
) -> list[str]:
    """Register all available built-in tools onto `registry` and return registered tool names."""

    # ── 1. Filesystem Tools (dsh-tool-fs) ─────────────────────────────────────
    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read a file from the workspace with 1-indexed line numbers.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "default": 1},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
            handler=lambda args: {
                "path": args["path"],
                "content": file_manager.read_text(
                    args["path"],
                    offset=int(args.get("offset", 1)),
                    limit=int(args["limit"]) if args.get("limit") is not None else None,
                )[0],
            },
            mutating=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="write_file",
            description="Write or create a file atomically within the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            handler=lambda args: {
                "path": args["path"],
                "bytes_written": file_manager.write_text(args["path"], args["content"]),
            },
            mutating=True,
            parallel_safe=False,
        )
    )

    def _edit_handler(args: dict[str, Any]) -> dict[str, Any]:
        _, diff_text = file_manager.edit_text(
            args["path"],
            old_str=args["old_str"],
            new_str=args["new_str"],
            replace_all=bool(args.get("replace_all", False)),
        )
        return {"path": args["path"], "diff": diff_text}

    registry.register(
        ToolDefinition(
            name="edit_file",
            description="Perform exact substring replacement on an observed file and return unified diff.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "required": ["path", "old_str", "new_str"],
            },
            handler=_edit_handler,
            mutating=True,
            parallel_safe=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="str_replace_editor",
            description="Official dsh str_replace_editor alias for exact substring replacement.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "required": ["path", "old_str", "new_str"],
            },
            handler=_edit_handler,
            mutating=True,
            parallel_safe=False,
        )
    )

    if searcher is not None:
        registry.register(
            ToolDefinition(
                name="glob_files",
                description="Find files in the workspace matching a glob pattern.",
                parameters={
                    "type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"],
                },
                handler=lambda args: {"matches": searcher.glob(args["pattern"])},
                mutating=False,
            )
        )
        registry.register(
            ToolDefinition(
                name="grep_search",
                description="Search file contents across the workspace using regex or literal pattern.",
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "include_glob": {"type": "string"},
                    },
                    "required": ["pattern"],
                },
                handler=lambda args: {
                    "matches": [
                        m.model_dump()
                        for m in searcher.grep(
                            args["pattern"],
                            include_glob=args.get("include_glob"),
                        )
                    ]
                },
                mutating=False,
            )
        )

    # ── 2. Sandbox & Background Job Tools (dsh-tool-pwsh / dsh-tool-jobs) ─────
    if sandbox is not None:
        registry.register(
            ToolDefinition(
                name="run_command",
                description="Execute a shell command inside the contained workspace sandbox.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "number"},
                        "run_in_background": {"type": "boolean", "default": False},
                    },
                    "required": ["command"],
                },
                handler=lambda args: (
                    job_manager.start_job(
                        args["command"],
                        owner_session_id=session.session_id,
                    ).model_dump()
                    if args.get("run_in_background") and job_manager is not None
                    else sandbox.execute(
                        args["command"],
                        timeout=float(args["timeout"]) if args.get("timeout") is not None else None,
                    ).model_dump()
                ),
                mutating=False,
                parallel_safe=False,
            )
        )

    if job_manager is not None:
        registry.register(
            ToolDefinition(
                name="job_list",
                description="List background jobs owned by the active session.",
                parameters={"type": "object", "properties": {}},
                handler=lambda _: {
                    "jobs": [j.model_dump() for j in job_manager.list_jobs(session.session_id)]
                },
            )
        )
        registry.register(
            ToolDefinition(
                name="job_output",
                description="Read stdout/stderr and status of a background job.",
                parameters={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string"},
                        "wait_timeout": {"type": "number", "default": 0.0},
                    },
                    "required": ["job_id"],
                },
                handler=lambda args: job_manager.get_job_output(
                    args["job_id"],
                    wait_timeout=float(args.get("wait_timeout", 0.0)),
                ).model_dump(),
            )
        )
        registry.register(
            ToolDefinition(
                name="job_kill",
                description="Terminate a running background job and its process tree.",
                parameters={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
                handler=lambda args: job_manager.kill_job(args["job_id"]).model_dump(),
                parallel_safe=False,
            )
        )

    # ── 3. Autonomy Tools: Todo, Plan, Goal ───────────────────────────────────
    if todo_manager is not None:
        registry.register(
            ToolDefinition(
                name="todo_write",
                description="Record and update the session task list (`pending`, `in_progress`, `completed`).",
                parameters={
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed"],
                                    },
                                },
                                "required": ["content", "status"],
                            },
                        }
                    },
                    "required": ["todos"],
                },
                handler=lambda args: {
                    "todos": [
                        t.model_dump()
                        for t in todo_manager.write_todos(session, args.get("todos", []))
                    ]
                },
                mutating=True,
                parallel_safe=False,
            )
        )

    if plan_manager is not None:
        registry.register(
            ToolDefinition(
                name="exit_plan_mode",
                description="Submit the complete implementation plan markdown (starting with `# `) for approval.",
                parameters={
                    "type": "object",
                    "properties": {"plan_markdown": {"type": "string"}},
                    "required": ["plan_markdown"],
                },
                handler=lambda args: plan_manager.exit_plan_mode(
                    session, args["plan_markdown"]
                ).model_dump(),
                mutating=False,
                parallel_safe=False,
            )
        )

    if goal_manager is not None:
        registry.register(
            ToolDefinition(
                name="create_goal",
                description="Create and arm a same-session autonomous goal.",
                parameters={
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "max_goal_rounds": {"type": "integer", "default": 20},
                    },
                    "required": ["objective"],
                },
                handler=lambda args: goal_manager.create_goal(
                    session,
                    objective=args["objective"],
                    max_goal_rounds=int(args.get("max_goal_rounds", 20)),
                ).model_dump(),
                parallel_safe=False,
            )
        )
        registry.register(
            ToolDefinition(
                name="get_goal",
                description="Inspect the current session goal state.",
                parameters={"type": "object", "properties": {}},
                handler=lambda _: {
                    "goal": (
                        g.model_dump() if (g := goal_manager.get_goal(session)) is not None else None
                    )
                },
            )
        )
        registry.register(
            ToolDefinition(
                name="update_goal",
                description="Update goal phase (`active`, `paused`, `blocked`, `complete`) or objective.",
                parameters={
                    "type": "object",
                    "properties": {
                        "phase": {
                            "type": "string",
                            "enum": ["active", "paused", "blocked", "complete"],
                        },
                        "objective": {"type": "string"},
                        "blocked_reason": {"type": "object"},
                    },
                },
                handler=lambda args: goal_manager.update_goal(
                    session,
                    phase=args.get("phase"),
                    objective=args.get("objective"),
                    blocked_reason=args.get("blocked_reason"),
                ).model_dump(),
                parallel_safe=False,
            )
        )

    # ── 4. Skill & Session Query Tools ────────────────────────────────────────
    if skill_registry is not None:
        registry.register(
            ToolDefinition(
                name="load_skill",
                description="Load full instructions for a named skill from the skill registry.",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                handler=lambda args: skill_registry.get_skill(args["name"]).model_dump(),
            )
        )

    if query_service is not None:
        registry.register(
            ToolDefinition(
                name="session_search",
                description="Search historical events in the session log by keyword or regex.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["query"],
                },
                handler=lambda args: {
                    "matches": [
                        e.model_dump()
                        for e in query_service.search_events(
                            session,
                            query=args["query"],
                            limit=int(args.get("limit", 20)),
                        )
                    ]
                },
            )
        )

    # ── 5. Subagent Tools (`subagent`, `subagent_fork`, `send_message`, `list_agents`) ─
    if subagent_manager is not None:
        registry.register(
            ToolDefinition(
                name="subagent",
                description="Spawn a fresh isolated subagent to handle a subtask.",
                parameters={
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["role", "prompt"],
                },
                handler=lambda args: subagent_manager.spawn(
                    session, role=args["role"], prompt=args["prompt"]
                ).model_dump(),
            )
        )
        registry.register(
            ToolDefinition(
                name="subagent_fork",
                description="Fork a subagent seeded with the parent's completed-turn prefix for KV-Cache reuse.",
                parameters={
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["role", "prompt"],
                },
                handler=lambda args: subagent_manager.fork(
                    session, role=args["role"], prompt=args["prompt"]
                ).model_dump(),
            )
        )
        registry.register(
            ToolDefinition(
                name="send_message",
                description="Send a follow-up message to an existing subagent.",
                parameters={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["agent_id", "message"],
                },
                handler=lambda args: subagent_manager.send_message(
                    args["agent_id"], args["message"]
                ).model_dump(),
            )
        )
        registry.register(
            ToolDefinition(
                name="list_agents",
                description="List all child subagents spawned or forked from this session.",
                parameters={"type": "object", "properties": {}},
                handler=lambda _: {
                    "agents": [
                        a.model_dump() for a in subagent_manager.list_agents(session.session_id)
                    ]
                },
            )
        )

    # ── 6. User Questions & Deliverables (`ask_user_question`, `present`) ─────
    if question_manager is not None:
        registry.register(
            ToolDefinition(
                name="ask_user_question",
                description="Ask the user a structured multiple-choice question.",
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "allow_multiple": {"type": "boolean", "default": False},
                    },
                    "required": ["question"],
                },
                handler=lambda args: question_manager.ask(
                    session,
                    question=args["question"],
                    options=args.get("options"),
                    allow_multiple=bool(args.get("allow_multiple", False)),
                ).model_dump(),
            )
        )

    if deliverable_manager is not None:
        registry.register(
            ToolDefinition(
                name="present_deliverable",
                description="Declare an explicit workspace file deliverable for the user.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string", "default": ""},
                    },
                    "required": ["path", "title"],
                },
                handler=lambda args: deliverable_manager.present(
                    session,
                    path=args["path"],
                    title=args["title"],
                    description=args.get("description", ""),
                ).model_dump(),
            )
        )

    # ── 7. EduForge LabKit Physics & Circuit Experiment Tools (`experiment_*`) ─
    if labkit_bridge is not None:
        registry.register(
            ToolDefinition(
                name="experiment_recipes",
                description="List available physics, circuit, and optics experiment templates and recipes.",
                parameters={
                    "type": "object",
                    "properties": {"template_id": {"type": "string"}},
                },
                handler=lambda args: labkit_bridge.experiment_recipes(args.get("template_id")),
            )
        )
        registry.register(
            ToolDefinition(
                name="experiment_validate",
                description="Run L1 parameter range validation and analytic prediction for an experiment recipe.",
                parameters={
                    "type": "object",
                    "properties": {
                        "recipe_id": {"type": "string"},
                        "params": {"type": "object"},
                        "why_recipe": {"type": "string"},
                        "student_task": {"type": "string"},
                    },
                    "required": ["recipe_id"],
                },
                handler=lambda args: labkit_bridge.experiment_validate(
                    recipe_id=args["recipe_id"],
                    params=args.get("params"),
                    why_recipe=args.get("why_recipe", "Matched curriculum objective"),
                    student_task=args.get("student_task", "Measure and verify physical law"),
                ),
            )
        )
        registry.register(
            ToolDefinition(
                name="experiment_simulate",
                description="Run L2 physics engine simulation and reconcile against L1 analytic predictions.",
                parameters={
                    "type": "object",
                    "properties": {
                        "recipe_id": {"type": "string"},
                        "params": {"type": "object"},
                        "why_recipe": {"type": "string"},
                        "student_task": {"type": "string"},
                    },
                    "required": ["recipe_id"],
                },
                handler=lambda args: labkit_bridge.experiment_simulate(
                    recipe_id=args["recipe_id"],
                    params=args.get("params"),
                    why_recipe=args.get("why_recipe", "Matched curriculum objective"),
                    student_task=args.get("student_task", "Measure and verify physical law"),
                ),
            )
        )
        registry.register(
            ToolDefinition(
                name="experiment_render",
                description="Render standalone offline HTML and evidence JSON for an experiment.",
                parameters={
                    "type": "object",
                    "properties": {
                        "recipe_id": {"type": "string"},
                        "params": {"type": "object"},
                        "why_recipe": {"type": "string"},
                        "student_task": {"type": "string"},
                        "out_name": {"type": "string"},
                    },
                    "required": ["recipe_id"],
                },
                handler=lambda args: labkit_bridge.experiment_render(
                    recipe_id=args["recipe_id"],
                    params=args.get("params"),
                    why_recipe=args.get("why_recipe", "Matched curriculum objective"),
                    student_task=args.get("student_task", "Measure and verify physical law"),
                    out_name=args.get("out_name"),
                ),
            )
        )
        registry.register(
            ToolDefinition(
                name="experiment_verify",
                description="Verify rendered experiment HTML for offline CSP compliance and evidence hash.",
                parameters={
                    "type": "object",
                    "properties": {
                        "html_path": {"type": "string"},
                        "evidence_path": {"type": "string"},
                    },
                    "required": ["html_path", "evidence_path"],
                },
                handler=lambda args: labkit_bridge.experiment_verify(
                    html_path=args["html_path"],
                    evidence_path=args["evidence_path"],
                ),
            )
        )
        registry.register(
            ToolDefinition(
                name="experiment_build",
                description="Build full 5-artifact experiment delivery package (L1 -> L2 -> HTML -> L3 -> Teacher/Student/Manifest).",
                parameters={
                    "type": "object",
                    "properties": {
                        "recipe_id": {"type": "string"},
                        "params": {"type": "object"},
                        "why_recipe": {"type": "string"},
                        "student_task": {"type": "string"},
                        "out_name": {"type": "string"},
                    },
                    "required": ["recipe_id"],
                },
                handler=lambda args: labkit_bridge.experiment_build(
                    recipe_id=args["recipe_id"],
                    params=args.get("params"),
                    why_recipe=args.get("why_recipe", "Matched curriculum objective"),
                    student_task=args.get("student_task", "Measure and verify physical law"),
                    out_name=args.get("out_name"),
                ),
            )
        )

    return registry.list_names()
