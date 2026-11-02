# subagent/ — 子智能体派生与 KV-Cache 共享分叉子系统

> 2026-10-31 状态修正：默认 runner 未绑定模型，当前会生成完成文本；spawn/fork 的会话结构测试不证明真实委派执行，KV-cache 命中也未在供应商侧实测。

**职责**：对应上游 `packages/subagent/`（`@deepseek-ai/dsh-subagent`、`@deepseek-ai/dsh-subagent-spawn-in-process`、`@deepseek-ai/dsh-subagent-fork-in-process`、`@deepseek-ai/dsh-tool-subagent-control`），支持主 Agent 将子任务委派给独立上下文的 `spawn` 子智能体或继承父会话前缀的 `fork` 子智能体，并提供 `send_message`、`list_agents`、`interrupt_agent` 全生命周期控制。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 导出 `SubagentManager`、`SubagentRecord`、`SubagentSummary`、`completed_turn_prefix` |
| [`manager.py`](manager.py) | 已实测 | `completed_turn_prefix` 已完成轮次前缀切片、`spawn`/`fork` 两种委派后端、递归深度上限保护（`max_depth`）及子智能体控制接口 |

## 与上下层的关系

- **上层消费者**：上游 `tools`（暴露 `subagent`、`subagent_fork`、`send_message`、`list_agents`、`interrupt_agent` 工具）与 `loop` 调度器。
- **下层依赖**：[`../session/`](../session/README.md)（每个子智能体拥有独立的 `Session` 实例与事件日志）。

## 已知的坑与纪律

1. **为什么 `fork` 切片停在最后一个 `turn/end`**：当前正在执行 `subagent_fork` 工具调用的轮次尚未闭合（只有 `tool/call` 尚无 `tool/result`），若直接拷贝全量日志会导致子会话的消息历史不平衡而报错。因此 `completed_turn_prefix` 严格切片至最后一个 `turn/end`，既保证合法重放，又实现 100% KV-Cache 前缀复用。
2. **递归深度硬门**：默认 `max_depth = 3`，超过深度的子智能体派生会被 `PermissionError` 阻断，防止无限递归派生。
