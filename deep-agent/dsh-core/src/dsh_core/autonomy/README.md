# autonomy/ — 规划模式、任务列表与目标自治驱动子系统

**职责**：对应上游 `packages/todo/`（`@deepseek-ai/dsh-tool-todo`）、`packages/plan/`（`@deepseek-ai/dsh-plan-mode`）以及 `packages/goal/`（`@deepseek-ai/dsh-goal`、`@deepseek-ai/dsh-goal-round-driver`），赋予 Agent 结构化任务跟踪、先规划后执行的只读探索门禁、以及跨多轮自动持续推进直至目标达成的自治能力。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 导出 `TodoManager`、`PlanModeManager`、`GoalManager`、`GoalRoundDriver` 等核心符号 |
| [`todo.py`](todo.py) | 已实测 | 事件溯源 `todo/write` 全表替换、非空唯一性校验、`allow_parallel_in_progress` 约束与会话投影折叠 |
| [`plan_mode.py`](plan_mode.py) | 已实测 | 规划模式提示词注入、变更类工具拦截（`PlanModeViolationError`）与 `exit_plan_mode` 审批流转 |
| [`goal.py`](goal.py) | 已实测 | 目标状态机（`active`/`paused`/`blocked`/`complete`）、CAS 版本号核验、3 轮最小 `blocked` 下限（`MIN_ROUNDS_BEFORE_BLOCK = 3`）与自动轮次推进驱动器 |

## 与上下层的关系

- **上层消费者**：上游 `tools`（暴露 `todo_write`、`exit_plan_mode`、`create_goal`、`update_goal`、`get_goal` 工具）与 `loop` 调度器（在每轮结束时通过 `GoalRoundDriver` 判断是否自动发起下一轮）。
- **下层依赖**：[`../session/`](../session/README.md)（所有状态变更均落为不可篡改的 `SessionEvent` 并注册进 `SessionProjectionRegistry`）。

## 已知的坑与纪律

1. **`blocked` 三轮下限**：为防止模型遇到微小报错就轻易放弃并声称阻塞，`update_goal(phase="blocked")` 严格要求 `rounds_started >= 3`，未满 3 轮将抛出 `GoalError`。
2. **Plan 模式缓存稳定性**：与上游一致，Plan 模式不从模型请求中删减工具 Schema（保住 KV-Cache 前缀），而是通过系统提示词节与 `PlanModeManager.check_tool_allowed` 在执行前门禁拦截。
