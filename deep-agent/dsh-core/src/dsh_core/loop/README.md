# `src/dsh_core/loop/` — Agent 执行主循环与预设注册表（对标 `packages/agent-loop` + `packages/agent-preset`）

> 2026-10-31 状态修正：这是研究原型的组合循环，默认使用 MockLlmClient，子智能体与实验桥接存在入口 README 记录的替代实现，不能宣称官方完整运行能力。

## 1. 职责

把 `dsh-core` 的全部 11 个底层与中层子系统（`file`、`sandbox`、`memory`、`session`、`guard`、`autonomy`、`skill`、`subagent`、`interaction`、`labkit`、`tools`）串联为真正可驱动多轮工具调用、长时自主迭代（`/goal`）、子智能体派生（`spawn`/`fork`）和物理实验生成的**完整可执行 Agent 运行时内核**。

## 2. 内容

| 文件 | 对标上游包 | 核心类与职责 |
|---|---|---|
| [`preset.py`](preset.py) | `packages/agent-preset/agent-preset`、`packages/agent-preset/agent-preset-registry` | `AgentPreset`、`AgentPresetRegistry`、`DEFAULT_PRESETS`：管理 4 套开箱即用预设（`standard` 全能 28 工具、`physics-lab` 物理教研与 LabKit 专项、`plan` 只读架构规划、`minimal` 极简 6 工具） |
| [`agent_loop.py`](agent_loop.py) | `packages/agent-loop/agent-loop` | `AgentLoop`、`TurnRunSummary`：完整的 Turn 生命周期状态机（`@file` 引用展开 → `AGENTS.md` / `SKILL.md` / `PlanMode` / `Goal` 系统提示词组装 → 模型决策与工具分派 → `ToolRegistry` 门禁/超时/重复提醒/Spill落盘 → `WorkspaceChangeTracker` 变更快照 → `MemoryManager` 预算检查与自动压缩 → `GoalRoundDriver` 多轮自治续跑） |
| [`__init__.py`](__init__.py) | — | 导出 `AgentLoop`、`TurnRunSummary`、`AgentPreset`、`AgentPresetRegistry`、`DEFAULT_PRESETS`、`PHYSICS_LAB_TOOLS`、`MINIMAL_TOOLS` |

## 3. 与上下层的关系

- **上层**：由 [`src/dsh_core/__init__.py`](../__init__.py) 导出，作为业务侧（ICT 物理教学 Agent、评测脚本、Web/CLI 宿主）直接实例化的顶层入口。
- **同层协作**：汇总编排 [`file/`](../file/README.md)、[`sandbox/`](../sandbox/README.md)、[`memory/`](../memory/README.md)、[`session/`](../session/README.md)、[`guard/`](../guard/README.md)、[`autonomy/`](../autonomy/README.md)、[`skill/`](../skill/README.md)、[`subagent/`](../subagent/README.md)、[`interaction/`](../interaction/README.md)、[`labkit/`](../labkit/README.md)、[`tools/`](../tools/README.md)。

## 4. 已知的坑与纪律

- **模型回调解耦（BYOM）**：`AgentLoop.run_turn(user_prompt, model_fn)` 通过可注入的 `model_fn(context_messages, system_prompt, tool_schemas)` 与具体 LLM SDK 解耦，既支持对接 OpenAI/DeepSeek API，也支持在单元测试中使用确定性状态机模拟多步工具调用。
- **Goal 自治防死循环**：`run_with_goal_driver` 严格受 `max_goal_rounds` 与 `GoalManager` 的 `MIN_ROUNDS_BEFORE_BLOCK = 3` 约束，防止无人值守任务无限空转或首轮草率放弃。
