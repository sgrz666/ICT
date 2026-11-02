"""Declarative agent preset registry (@deepseek-ai/dsh-agent-preset & @deepseek-ai/dsh-agent-preset-registry).

Defines capability compositions (`standard`, `physics-lab`, `plan`, `minimal`)
controlling which tools, persona instructions, and modes are mounted for a session.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentPreset(BaseModel):
    """Declarative capability composition for an Agent session."""

    id: str
    title: str
    description: str
    persona_prefix: str
    allowed_tools: set[str] | None = None
    enable_plan_mode: bool = False
    enable_labkit_section: bool = True
    enforce_observation: bool = True


PHYSICS_LAB_TOOLS: set[str] = {
    "experiment_recipes",
    "experiment_validate",
    "experiment_simulate",
    "experiment_render",
    "experiment_verify",
    "experiment_build",
    "ask_user_question",
    "present_deliverable",
}

MINIMAL_TOOLS: set[str] = {
    "read_file",
    "glob_files",
    "grep_search",
    "ask_user_question",
}

DEFAULT_PRESETS: dict[str, AgentPreset] = {
    "standard": AgentPreset(
        id="standard",
        title="启智 · 标准全能模式 (Standard Agent)",
        description="挂载全套文件管理、沙箱执行、长时记忆、规划目标、子智能体与物理实验工具。",
        persona_prefix=(
            "You are the ICT EduForge AI Agent (启智AGENT), a full-featured engineering and "
            "educational assistant with access to workspace files, sandboxed execution, "
            "planning, subagents, and verified physics/circuit experiment tools."
        ),
        allowed_tools=None,
        enable_plan_mode=False,
        enable_labkit_section=True,
        enforce_observation=True,
    ),
    "physics-lab": AgentPreset(
        id="physics-lab",
        title="格物 · 物理实验工坊 (Physics Lab Preset)",
        description="教师端专用实验生成模式：仅挂载六个 experiment_* 原生工具、提问与交付卡片，禁止手写 HTML 或执行任意 Shell。",
        persona_prefix=(
            "你是「格物 · 物理实验工坊」专属智能体。你只能通过 experiment_* 工具一句话生成经过 L1/L2/L3 对账的离线物理与电路实验包。"
        ),
        allowed_tools=set(PHYSICS_LAB_TOOLS),
        enable_plan_mode=False,
        enable_labkit_section=True,
        enforce_observation=True,
    ),
    "plan": AgentPreset(
        id="plan",
        title="架构规划模式 (Plan Mode)",
        description="先只读探索代码库并提交完整 Markdown 方案，经 exit_plan_mode 审批通过后再自动解锁代码修改。",
        persona_prefix=(
            "You are the ICT EduForge AI Agent starting in Plan Mode. Explore the workspace "
            "using read-only tools and submit a decision-complete plan via exit_plan_mode."
        ),
        allowed_tools=None,
        enable_plan_mode=True,
        enable_labkit_section=True,
        enforce_observation=True,
    ),
    "minimal": AgentPreset(
        id="minimal",
        title="极简只读问答模式 (Minimal Read-Only)",
        description="仅挂载只读文件查看与搜索工具，适用于代码导读与理论答疑。",
        persona_prefix="You are a concise read-only educational tutor and code reader.",
        allowed_tools=set(MINIMAL_TOOLS),
        enable_plan_mode=False,
        enable_labkit_section=False,
        enforce_observation=False,
    ),
}


class AgentPresetRegistry:
    """Registry of available AgentPresets (`@deepseek-ai/dsh-agent-preset-registry`)."""

    def __init__(self, default_preset_id: str = "standard"):
        self._presets: dict[str, AgentPreset] = {
            k: v.model_copy(deep=True) for k, v in DEFAULT_PRESETS.items()
        }
        if default_preset_id not in self._presets:
            raise ValueError(f"Unknown default preset: {default_preset_id!r}")
        self.default_preset_id = default_preset_id

    def register(self, preset: AgentPreset) -> None:
        self._presets[preset.id] = preset

    def get(self, preset_id: str | None = None) -> AgentPreset:
        target = preset_id or self.default_preset_id
        if target not in self._presets:
            raise KeyError(f"Unknown agent preset: {target!r}")
        return self._presets[target]

    def list_presets(self) -> list[AgentPreset]:
        return [self._presets[k] for k in sorted(self._presets.keys())]

    def list_ids(self) -> list[str]:
        return sorted(self._presets.keys())
