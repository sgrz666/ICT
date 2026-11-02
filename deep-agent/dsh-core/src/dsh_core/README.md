# dsh_core — 核心智能体基础设施包 (Core Agent Infrastructure Package)

**职责**：提供纯 Python 实现的完整工业级 Agent 运行时与基础设施内核（对标 `deepseek-harness` 保留的 42 个核心类别）。整合文件管理与先读后写门禁（`file`）、沙箱隔离与后台作业（`sandbox`）、会话与声明式折叠投影（`session`）、长时记忆与 Spill 落盘（`memory`）、防死循环与超时守卫（`guard`）、Todo/Plan/Goal 长程自治（`autonomy`）、技能发现与动态系统提示词（`skill`）、子智能体派生与 KV-Cache 前缀分叉（`subagent`）、用户审批/提问/交付物与变更追踪（`interaction`）、EduForge 物理与电路实验桥接（`labkit`）、27 项内置工具流水线（`tools`）以及完整执行主循环与预设注册表（`loop`）共 **12 大子系统**。

## 内容

| 模块 / 文件 | 状态 | 说明 |
|---|---|---|
| [`file/`](file/README.md) | 已实测 | 文件管理子系统：带行号窗口读、先读后写 CAS 门禁（`FsObservationPolicy`）、原子写、唯一子串替换、3 行上下文 diff、防逃逸校验与纯 Python 检索 |
| [`sandbox/`](sandbox/README.md) | 已实测 | 沙箱与后台作业子系统：Windows 原生子进程受控执行、`BackgroundJobManager` 后台长任务管理、`taskkill /F /T` 进程树强杀、三档策略检查与 Mock 沙箱 |
| [`session/`](session/README.md) | 已实测 | 会话与投影子系统：格式版本 4 事件溯源、表面投影遮蔽（Surface）、声明式折叠投影（`sessionStats`/`turnOutline`/`turnBoundary`）、`SessionQueryService` 与 JSONL 持久化 |
| [`memory/`](memory/README.md) | 已实测 | 长时记忆与 Spill 子系统：4 字符/Token 估算器、超限输出落盘保留（`SpillStore`/`SpillPolicy`）、多模态图像卸载（`ImageOffloadPolicy`）与八段式摘要压缩引擎 |
| [`guard/`](guard/README.md) | 已实测 | 安全守卫子系统：重复工具调用检测与阶梯式提醒（`RepeatToolReminder`）及按工具粒度超时熔断（`ToolTimeoutPolicy`） |
| [`autonomy/`](autonomy/README.md) | 已实测 | 规划与长时自治子系统：事件溯源任务列表（`TodoManager`）、只读规划门禁（`PlanModeManager`）与 3 轮防早退自治目标引擎（`GoalManager` + `GoalRoundDriver`） |
| [`skill/`](skill/README.md) | 已实测 | 技能与提示词子系统：`.agents/skills/*/SKILL.md` 发现加载（`SkillRegistry`）、`AGENTS.md` 注入、`@file` 引用展开与 KV-Cache 友好的 `SystemPromptBuilder` |
| [`subagent/`](subagent/README.md) | 已实测 | 子智能体协同子系统：全新隔离派生（`spawn`）与继承 `completed_turn_prefix` 复用 KV-Cache 的分叉（`fork`）及消息/中断控制 |
| [`interaction/`](interaction/README.md) | 已实测 | 人机交互与变更子系统：三档权限预设与审批（`ApprovalManager`）、结构化提问（`UserQuestionManager`）、交付物卡片（`DeliverableManager`）与单轮文件变更快照（`WorkspaceChangeTracker`） |
| [`labkit/`](labkit/README.md) | 已实测 | 物理与电路实验子系统：内置抛体、单摆、欧姆定律电路、凸透镜成像 4 大领域 9 套配方与 6 个 `experiment_*` 工具，一键产出 5 件套教学实验包 |
| [`tools/`](tools/README.md) | 已实测 | 工具注册表与内置工具集：三阶段执行流水线（`pre -> timeout -> post`）与 27 个开箱即用的内置工具定义 |
| [`loop/`](loop/README.md) | 已实测 | Agent 主循环与预设子系统：`AgentPresetRegistry`（`standard`/`physics-lab`/`plan`/`minimal`）与完整多步闭环驱动器 `AgentLoop` |
| [`__init__.py`](__init__.py) | 已实测 | 顶级包统一导出，提供一站式 `import dsh_core` 调用入口（`v0.2.0`） |

## 与上下层的关系

- **上层依赖**：位于 [`../`](../README.md)（`src/` 源码根目录），受 [`../../pyproject.toml`](../../pyproject.toml) 构建描述。
- **下层支撑**：包含 12 个领域子系统目录（`file/`, `sandbox/`, `session/`, `memory/`, `guard/`, `autonomy/`, `skill/`, `subagent/`, `interaction/`, `labkit/`, `tools/`, `loop/`）。
- **外部应用**：上层教育应用或测试套件通过 `from dsh_core import FileManager, ProcessSandbox, Session, CompactionEngine` 直接消费核心基础设施。

## 已知的坑与纪律

1. **导入解耦**：顶层 `__init__.py` 统一导出的类均已经过弱耦合设计，未安装可选网络库 `httpx` 时不影响基础模块使用。
2. **纯 Python 保证**：所有模块实现杜绝 C++ native 动态链接库或 Node.js 外部运行时依赖，保证在任意标准 Python 3.10+ 环境下秒级加载。
3. **安全第一**：涉及工作区路径的操作默认开启边界防护（`enforce_containment=True`），杜绝越界穿透。
