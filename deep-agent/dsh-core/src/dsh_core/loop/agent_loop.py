"""Concrete Agent Loop engine (@deepseek-ai/dsh-agent-loop).

Orchestrates the full DeepSeek Harness turn/step lifecycle across all 12
subsystems:
- Workspace instruction & skill catalog injection (`SystemPromptBuilder`)
- `@file` reference resolution (`FileReferenceResolver`)
- Per-turn workspace file change tracking (`WorkspaceChangeTracker`)
- Multi-step tool execution pipeline (`ToolRegistry` with `PlanModeManager`,
  `ApprovalManager`, `FsObservationPolicy`, `ToolTimeoutPolicy`, `SpillPolicy`,
  and `RepeatToolReminder`)
- Automatic context budget evaluation & 8-section compaction (`CompactionEngine`)
- Automatic goal round continuation (`GoalRoundDriver`)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..autonomy.goal import GoalManager, GoalRoundDriver
from ..autonomy.plan_mode import PlanModeManager
from ..autonomy.todo import TodoManager
from ..file.manager import FileManager
from ..file.search import WorkspaceSearcher
from ..guard.repeat_reminder import RepeatToolReminder
from ..guard.timeout_policy import ToolTimeoutPolicy
from ..interaction.approval import ApprovalManager, PresetName
from ..interaction.deliverables import DeliverableManager, TurnWorkspaceChanges, WorkspaceChangeTracker
from ..interaction.questions import UserQuestionManager
from ..labkit.bridge import LABKIT_SYSTEM_PROMPT_SECTION, LabKitBridge
from ..memory.compaction import CompactionEngine
from ..memory.pruner import OutputPruner
from ..memory.spill import SpillPolicy, SpillStore
from ..memory.token_meter import TokenMeter
from ..sandbox.jobs import BackgroundJobManager
from ..sandbox.process_runner import ProcessSandbox
from ..session.llm_client import BaseLlmClient, MockLlmClient
from ..session.models import Message
from ..session.persistence import JsonlPersistence
from ..session.projection import SessionProjectionRegistry, SessionQueryService
from ..session.state_machine import Session
from ..skill.instructions import FileReferenceResolver, InstructionLoader
from ..skill.skill_registry import SkillRegistry
from ..skill.system_prompt import SystemPromptBuilder
from ..subagent.manager import SubagentManager
from ..tools.builtin_tools import register_builtin_tools
from ..tools.registry import ToolCallRequest, ToolExecutionResult, ToolRegistry
from .preset import AgentPreset, AgentPresetRegistry


class TurnRunSummary(BaseModel):
    """Summary of a completed AgentLoop turn."""

    turn: int
    steps_executed: int
    final_assistant_text: str
    tool_calls_made: list[str] = Field(default_factory=list)
    compacted: bool = False
    workspace_changes: TurnWorkspaceChanges | None = None


class AgentLoop:
    """Full-featured DeepSeek Harness Agent Loop tying together all 12 core subsystems."""

    def __init__(
        self,
        workspace_root: str | Path,
        llm_client: BaseLlmClient | None = None,
        session: Session | None = None,
        persistence: JsonlPersistence | None = None,
        preset_id: str = "standard",
        permission_preset: PresetName = "workspace-write",
        context_limit_tokens: int = 64000,
        max_inline_tool_tokens: int = 12500,
        enforce_observation: bool | None = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.llm: BaseLlmClient = llm_client or MockLlmClient()
        self.preset_registry = AgentPresetRegistry(default_preset_id=preset_id)
        self.active_preset: AgentPreset = self.preset_registry.get(preset_id)

        self.session = session or Session(
            session_id="agent_session_01",
            cwd=str(self.workspace_root),
            persistence=persistence,
        )

        obs_enabled = (
            enforce_observation
            if enforce_observation is not None
            else self.active_preset.enforce_observation
        )

        # 1. File & Search
        self.file_manager = FileManager(
            workspace_root=self.workspace_root,
            enforce_containment=True,
            enforce_observation=obs_enabled,
        )
        self.searcher = WorkspaceSearcher(workspace_root=self.workspace_root)

        # 2. Interaction & Approval
        self.approval_manager = ApprovalManager(preset=permission_preset)
        self.question_manager = UserQuestionManager()
        self.deliverable_manager = DeliverableManager(workspace_root=self.workspace_root)
        self.change_tracker = WorkspaceChangeTracker(workspace_root=self.workspace_root)

        # 3. Sandbox & Background Jobs
        self.sandbox = ProcessSandbox(
            workspace_root=self.workspace_root,
            default_policy=self.approval_manager.current_preset.sandbox,
        )
        self.job_manager = BackgroundJobManager(
            workspace_root=self.workspace_root,
            default_policy=self.approval_manager.current_preset.sandbox,
        )

        # 4. Session Projections & Query
        self.projections = SessionProjectionRegistry(register_defaults=True)
        self.query_service = SessionQueryService()

        # 5. Memory, Spill & Compaction
        self.token_meter = TokenMeter()
        self.pruner = OutputPruner()
        self.spill_store = SpillStore(spill_root=self.workspace_root / ".dsh_spills")
        self.spill_policy = SpillPolicy(
            spill_store=self.spill_store,
            max_inline_tokens=max_inline_tool_tokens,
            token_meter=self.token_meter,
        )
        self.compaction_engine = CompactionEngine(
            llm_client=self.llm,
            token_meter=self.token_meter,
            pruner=self.pruner,
        )
        self.context_limit_tokens = context_limit_tokens

        # 6. Guards
        self.repeat_reminder = RepeatToolReminder()
        self.timeout_policy = ToolTimeoutPolicy()

        # 7. Autonomy (Todo, Plan, Goal)
        self.todo_manager = TodoManager(projection_registry=self.projections)
        self.plan_manager = PlanModeManager()
        if self.active_preset.enable_plan_mode:
            self.plan_manager.enter_plan_mode(self.session)
        self.goal_manager = GoalManager(projection_registry=self.projections)
        self.goal_driver = GoalRoundDriver(goal_manager=self.goal_manager)

        # 8. Skills, Instructions & System Prompt
        self.skill_registry = SkillRegistry()
        self.instruction_loader = InstructionLoader(workspace_root=self.workspace_root)
        self.file_ref_resolver = FileReferenceResolver(file_manager=self.file_manager)
        self.prompt_builder = SystemPromptBuilder(
            persona_prefix=self.active_preset.persona_prefix
        )

        # 9. Subagents
        self.subagent_manager = SubagentManager()

        # 10. LabKit Physics & Circuit Bridge
        self.labkit_bridge = LabKitBridge(
            output_root=self.workspace_root / "output" / "labkit"
        )

        # 11. Tool Registry & Waterfall Hooks
        self.tool_registry = ToolRegistry()
        register_builtin_tools(
            registry=self.tool_registry,
            session=self.session,
            file_manager=self.file_manager,
            searcher=self.searcher,
            sandbox=self.sandbox,
            job_manager=self.job_manager,
            todo_manager=self.todo_manager,
            plan_manager=self.plan_manager,
            goal_manager=self.goal_manager,
            skill_registry=self.skill_registry,
            subagent_manager=self.subagent_manager,
            question_manager=self.question_manager,
            deliverable_manager=self.deliverable_manager,
            query_service=self.query_service,
            labkit_bridge=self.labkit_bridge,
        )

        self._wire_pipeline_hooks()
        self._turn_counter = 0

    def _wire_pipeline_hooks(self) -> None:
        """Bind pre-execute, timeout, and post-execute hooks onto `tool_registry`."""

        def _pre_hook(session_id: str, req: ToolCallRequest) -> None:
            self.plan_manager.check_tool_allowed(session_id, req.name)
            self.approval_manager.check_approval(req.name, req.arguments)

        def _post_hook(
            session_id: str, req: ToolCallRequest, res: ToolExecutionResult
        ) -> ToolExecutionResult:
            # 1. Spill oversized outputs to disk before returning to model
            bounded_text, spill_ref = self.spill_policy.bound_tool_result(
                content=res.content,
                session_id=session_id,
                tool_name=req.name,
                call_id=req.call_id,
            )
            if spill_ref is not None:
                res.content = bounded_text
                res.spilled = True
                res.spill_path = spill_ref.path

            # 2. Check repeat-tool-reminder
            reminder = self.repeat_reminder.record_call(
                tool_name=req.name,
                arguments=req.arguments,
                session_id=session_id,
            )
            if reminder is not None:
                res.reminder = reminder
                res.content = f"{res.content}\n\n[GUARD REMINDER]\n{reminder}"

            return res

        self.tool_registry.add_pre_execute_hook(_pre_hook)
        self.tool_registry.add_post_execute_hook(_post_hook)
        self.tool_registry.set_timeout_runner(
            lambda tool_name, fn, args: self.timeout_policy.execute_with_timeout(
                tool_name, fn, args
            )
        )

    def _refresh_system_prompt(self) -> None:
        """Assemble dynamic sections (instructions, skills, plan mode, labkit) and apply to session."""
        instr = self.instruction_loader.load_instructions()
        if instr:
            self.prompt_builder.set_section("instructions", instr, priority=20)

        skill_cat = self.skill_registry.format_catalog_section()
        if skill_cat:
            self.prompt_builder.set_section("skills", skill_cat, priority=30)

        plan_sec = self.plan_manager.get_system_prompt_section(self.session.session_id)
        if plan_sec:
            self.prompt_builder.set_section("plan_mode", plan_sec, priority=40)
        else:
            self.prompt_builder.remove_section("plan_mode")

        if self.active_preset.enable_labkit_section:
            self.prompt_builder.set_section(
                "labkit", LABKIT_SYSTEM_PROMPT_SECTION, priority=50
            )
        else:
            self.prompt_builder.remove_section("labkit")

        self.prompt_builder.apply_to_session(self.session, in_history_update=True)

    async def run_turn_async(
        self,
        user_prompt: str,
        max_steps: int = 10,
    ) -> TurnRunSummary:
        """Execute a complete multi-step Agent Turn asynchronously."""
        self._turn_counter += 1
        turn_no = self._turn_counter

        self.change_tracker.begin_turn()
        self.session.append("turn/start", {"turn": turn_no})
        self._refresh_system_prompt()

        resolved_prompt = self.file_ref_resolver.resolve_prompt_references(user_prompt)
        self.session.append(
            "user/message",
            {"role": "user", "content": resolved_prompt},
            surface_op="append",
        )

        allowed_tools = self.active_preset.allowed_tools
        tool_schemas = self.tool_registry.schemas(allowed_names=allowed_tools)

        steps_executed = 0
        tool_calls_made: list[str] = []
        final_text = ""
        compacted_any = False

        for step_idx in range(1, max_steps + 1):
            steps_executed = step_idx
            self.session.append("step/start", {"turn": turn_no, "step": step_idx})

            # Refresh system prompt in case a previous step exited plan mode
            self._refresh_system_prompt()

            model_messages = self.session.derive_messages()
            assistant_msg: Message = await self.llm.generate(
                messages=model_messages,
                tools=tool_schemas,
            )

            raw_tcs: list[dict[str, Any]] = []
            if assistant_msg.tool_calls:
                for tc in assistant_msg.tool_calls:
                    raw_tcs.append(
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                    )

            self.session.append(
                "assistant/message",
                {
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": raw_tcs,
                },
                surface_op="append",
            )
            final_text = assistant_msg.content or ""

            if not raw_tcs:
                self.session.append("step/end", {"turn": turn_no, "step": step_idx})
                break

            # Execute tool calls through guarded pipeline
            for raw_tc in raw_tcs:
                res = self.tool_registry.execute_call(
                    raw_tc,
                    session_id=self.session.session_id,
                    allowed_names=allowed_tools,
                )
                tool_calls_made.append(res.name)
                self.session.append(
                    "tool/result",
                    {
                        "role": "tool",
                        "tool_call_id": res.call_id,
                        "name": res.name,
                        "content": res.content,
                        "is_error": res.is_error,
                        "spilled": res.spilled,
                    },
                    surface_op="append",
                )

            # Evaluate compaction after tool results settle
            if self.compaction_engine.compact_if_needed(
                self.session,
                context_limit=self.context_limit_tokens,
            ):
                compacted_any = True

            self.session.append("step/end", {"turn": turn_no, "step": step_idx})

        changes = self.change_tracker.end_turn(self.session, turn=turn_no)
        self.session.append("turn/end", {"turn": turn_no, "reason": "complete"})

        return TurnRunSummary(
            turn=turn_no,
            steps_executed=steps_executed,
            final_assistant_text=final_text,
            tool_calls_made=tool_calls_made,
            compacted=compacted_any,
            workspace_changes=changes,
        )

    def run_turn(self, user_prompt: str, max_steps: int = 10) -> TurnRunSummary:
        """Synchronous convenience wrapper around `run_turn_async`."""
        return asyncio.run(self.run_turn_async(user_prompt, max_steps=max_steps))

    async def run_with_goal_driver_async(
        self,
        initial_prompt: str,
        max_steps_per_turn: int = 10,
        max_continuation_turns: int = 10,
    ) -> list[TurnRunSummary]:
        """Run initial turn and automatically drive continuation turns while an active goal is armed."""
        summaries: list[TurnRunSummary] = []
        first = await self.run_turn_async(initial_prompt, max_steps=max_steps_per_turn)
        summaries.append(first)

        for _ in range(max_continuation_turns):
            if not self.goal_driver.is_drivable(self.session):
                break
            next_prompt = self.goal_driver.advance_round(self.session)
            if not next_prompt:
                break
            cont_summary = await self.run_turn_async(
                next_prompt, max_steps=max_steps_per_turn
            )
            summaries.append(cont_summary)

        return summaries

    def run_with_goal_driver(
        self,
        initial_prompt: str,
        max_steps_per_turn: int = 10,
        max_continuation_turns: int = 10,
    ) -> list[TurnRunSummary]:
        """Synchronous convenience wrapper around `run_with_goal_driver_async`."""
        return asyncio.run(
            self.run_with_goal_driver_async(
                initial_prompt,
                max_steps_per_turn=max_steps_per_turn,
                max_continuation_turns=max_continuation_turns,
            )
        )
