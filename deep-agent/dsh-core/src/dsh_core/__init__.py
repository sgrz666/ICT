"""dsh-core: Full-featured, decoupled Agent runtime extracted from DeepSeek Harness (dsh).

Provides 11 industrial-grade core subsystems in pure Python, mirroring the 42 retained
core package categories of upstream DeepSeek Harness while pruning telemetry, commercial
OAuth, POSIX-only SSH cluster runners, and experimental dependencies:

1. file: Containment-safe file management, read-before-write observation CAS guard
   (FsObservationPolicy), atomic writes, exact string replace editing, and contextual diffs.
2. sandbox: Windows-compatible controlled subprocess execution, background job lifecycle
   management (BackgroundJobManager), timeout management, process-tree termination, and
   permission policies.
3. session: Format version 4 event-sourced logs, surface projections, declarative
   projections (sessionStats, turnOutline, turnBoundary), session queries, turn/step loops,
   atomic JSONL persistence, and pluggable LLM clients.
4. memory: Token density estimation, tool output pruning, disk spill retention (SpillStore /
   SpillPolicy), multimodal image offload, and KV-cache friendly 8-section compaction.
5. guard: Repeat tool call detection (RepeatToolReminder) with deep argument canonicalization,
   and per-tool timeout policy (ToolTimeoutPolicy).
6. autonomy: Structured Todo list management (TodoManager), read-only Plan Mode
   (PlanModeManager), and autonomous Goal execution with MIN_ROUNDS_BEFORE_BLOCK=3
   (GoalManager & GoalRoundDriver).
7. skill: SKILL.md discovery & loading (SkillRegistry), hierarchical AGENTS.md instructions
   (InstructionLoader), @file reference expansion, and dynamic SystemPromptBuilder.
8. subagent: Subagent spawning and KV-cache prefix-reusing in-process fork (SubagentManager).
9. interaction: Permission presets & user approval gates (ApprovalManager), structured user
   questions (UserQuestionManager), deliverables (DeliverableManager), and turn workspace
   change tracking (WorkspaceChangeTracker).
10. labkit: Built-in ICT/EduForge physics & circuit experiment pipeline (LabKitBridge)
    supporting 9 recipes and 5-file educational experiment packages.
11. tools & loop: Unified ToolRegistry with 28 built-in tools, AgentPresetRegistry
    (standard, physics-lab, plan, minimal), and executable AgentLoop.
"""

from .autonomy import (
    MIN_ROUNDS_BEFORE_BLOCK,
    PLAN_MODE_SECTION,
    GoalActivation,
    GoalBlockReason,
    GoalError,
    GoalManager,
    GoalPhase,
    GoalRoundDriver,
    GoalSnapshot,
    GoalView,
    PlanModeManager,
    PlanModeViolationError,
    PlanSubmissionResult,
    TodoItem,
    TodoManager,
    TodoStatus,
    TodoValidationError,
    render_goal_round_prompt,
    validate_todo_list,
)
from .file import (
    FileManager,
    FsAmbiguousEditError,
    FsEditNotFoundError,
    FsError,
    FsNotFoundError,
    FsNotObservedError,
    FsObservation,
    FsObservationPolicy,
    FsSandboxDeniedError,
    FsStaleFileError,
    FsVersion,
    StrReplaceEditor,
    WorkspaceSearcher,
    assert_path_contained,
    format_diff_card,
    generate_context_diff,
    is_path_contained,
)
from .guard import (
    GENTLE_REMINDER,
    RepeatToolReminder,
    ToolCallTimeoutError,
    ToolTimeoutPolicy,
    canonicalize_arguments,
    detailed_reminder,
)
from .interaction import (
    DEFAULT_PERMISSION_PRESETS,
    ApprovalDeniedError,
    ApprovalManager,
    ApprovalPolicy,
    DeliverableItem,
    DeliverableManager,
    PermissionPreset,
    PresetName,
    TurnWorkspaceChanges,
    UserQuestion,
    UserQuestionManager,
    UserQuestionResponse,
    WorkspaceChangeTracker,
)
from .labkit import (
    LABKIT_SYSTEM_PROMPT_SECTION,
    RECIPES_CATALOG,
    LabKitBridge,
)
from .loop import (
    DEFAULT_PRESETS,
    MINIMAL_TOOLS,
    PHYSICS_LAB_TOOLS,
    AgentLoop,
    AgentPreset,
    AgentPresetRegistry,
    TurnRunSummary,
)
from .memory import (
    CHECKPOINT_PREAMBLE,
    COMPACTION_INSTRUCTION,
    EIGHT_SECTIONS,
    CompactionEngine,
    ImageOffloadPolicy,
    OutputPruner,
    SpillPolicy,
    SpillRef,
    SpillStore,
    TokenMeter,
    TokenUsage,
    format_spill_notice,
)
from .sandbox import (
    BackgroundJobManager,
    CommandResult,
    JobOutputSnapshot,
    JobStatus,
    JobSummary,
    MockSandboxProvider,
    PolicyChecker,
    PolicyViolationError,
    ProcessSandbox,
    SandboxPolicy,
    build_shell_command,
    detect_available_shells,
)
from .session import (
    SESSION_FORMAT_VERSION,
    BaseLlmClient,
    JsonlPersistence,
    Message,
    MockLlmClient,
    OpenAiCompatibleClient,
    ProjectionUnit,
    ReactLoopInbox,
    ReactLoopState,
    Role,
    Session,
    SessionEvent,
    SessionHeader,
    SessionProjectionRegistry,
    SessionQueryService,
    SessionStats,
    Step,
    SurfaceManager,
    SurfaceOp,
    ToolCall,
    ToolResult,
    Turn,
    TurnBoundaryState,
    TurnEndReason,
    TurnOutlineEntry,
    encode_session_id,
    project_key,
)
from .skill import (
    FileReferenceResolver,
    FilesystemSkillProvider,
    InstructionLoader,
    PromptSection,
    SkillDocument,
    SkillRegistry,
    SystemPromptBuilder,
    parse_skill_markdown,
)
from .subagent import (
    SubagentManager,
    SubagentMode,
    SubagentRecord,
    SubagentStatus,
    SubagentSummary,
    completed_turn_prefix,
)
from .tools import (
    PostExecuteHook,
    PreExecuteHook,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionResult,
    ToolRegistry,
    register_builtin_tools,
)

__version__ = "0.2.0"

__all__ = [
    "__version__",
    # 1. File Subsystem
    "FileManager",
    "FsObservationPolicy",
    "FsObservation",
    "FsVersion",
    "StrReplaceEditor",
    "WorkspaceSearcher",
    "assert_path_contained",
    "is_path_contained",
    "generate_context_diff",
    "format_diff_card",
    "FsError",
    "FsNotFoundError",
    "FsSandboxDeniedError",
    "FsAmbiguousEditError",
    "FsEditNotFoundError",
    "FsNotObservedError",
    "FsStaleFileError",
    # 2. Sandbox Subsystem
    "ProcessSandbox",
    "BackgroundJobManager",
    "JobStatus",
    "JobSummary",
    "JobOutputSnapshot",
    "MockSandboxProvider",
    "SandboxPolicy",
    "PolicyChecker",
    "PolicyViolationError",
    "CommandResult",
    "detect_available_shells",
    "build_shell_command",
    # 3. Session Subsystem
    "SESSION_FORMAT_VERSION",
    "Session",
    "SessionEvent",
    "SessionHeader",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
    "Turn",
    "Step",
    "TurnEndReason",
    "SurfaceOp",
    "SurfaceManager",
    "JsonlPersistence",
    "project_key",
    "encode_session_id",
    "ReactLoopInbox",
    "ReactLoopState",
    "BaseLlmClient",
    "MockLlmClient",
    "OpenAiCompatibleClient",
    "ProjectionUnit",
    "SessionStats",
    "TurnOutlineEntry",
    "TurnBoundaryState",
    "SessionProjectionRegistry",
    "SessionQueryService",
    # 4. Memory Subsystem
    "TokenMeter",
    "TokenUsage",
    "OutputPruner",
    "CompactionEngine",
    "CHECKPOINT_PREAMBLE",
    "EIGHT_SECTIONS",
    "COMPACTION_INSTRUCTION",
    "SpillRef",
    "SpillStore",
    "SpillPolicy",
    "format_spill_notice",
    "ImageOffloadPolicy",
    # 5. Guard Subsystem
    "RepeatToolReminder",
    "GENTLE_REMINDER",
    "detailed_reminder",
    "canonicalize_arguments",
    "ToolTimeoutPolicy",
    "ToolCallTimeoutError",
    # 6. Autonomy Subsystem
    "TodoItem",
    "TodoStatus",
    "TodoManager",
    "TodoValidationError",
    "validate_todo_list",
    "PLAN_MODE_SECTION",
    "PlanModeManager",
    "PlanModeViolationError",
    "PlanSubmissionResult",
    "MIN_ROUNDS_BEFORE_BLOCK",
    "GoalPhase",
    "GoalActivation",
    "GoalBlockReason",
    "GoalSnapshot",
    "GoalView",
    "GoalError",
    "GoalManager",
    "GoalRoundDriver",
    "render_goal_round_prompt",
    # 7. Skill & Prompt Subsystem
    "SkillDocument",
    "FilesystemSkillProvider",
    "SkillRegistry",
    "parse_skill_markdown",
    "InstructionLoader",
    "FileReferenceResolver",
    "PromptSection",
    "SystemPromptBuilder",
    # 8. Subagent Subsystem
    "SubagentMode",
    "SubagentStatus",
    "SubagentSummary",
    "SubagentRecord",
    "SubagentManager",
    "completed_turn_prefix",
    # 9. Interaction Subsystem
    "ApprovalPolicy",
    "PresetName",
    "PermissionPreset",
    "DEFAULT_PERMISSION_PRESETS",
    "ApprovalDeniedError",
    "ApprovalManager",
    "UserQuestion",
    "UserQuestionResponse",
    "UserQuestionManager",
    "DeliverableItem",
    "DeliverableManager",
    "TurnWorkspaceChanges",
    "WorkspaceChangeTracker",
    # 10. LabKit Subsystem
    "LabKitBridge",
    "RECIPES_CATALOG",
    "LABKIT_SYSTEM_PROMPT_SECTION",
    # 11. Tools & Loop Subsystem
    "ToolCallRequest",
    "ToolExecutionResult",
    "ToolDefinition",
    "ToolRegistry",
    "PreExecuteHook",
    "PostExecuteHook",
    "register_builtin_tools",
    "AgentPreset",
    "AgentPresetRegistry",
    "DEFAULT_PRESETS",
    "PHYSICS_LAB_TOOLS",
    "MINIMAL_TOOLS",
    "AgentLoop",
    "TurnRunSummary",
]
