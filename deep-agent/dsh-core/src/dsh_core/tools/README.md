# tools/ — 工具注册表、三段式守卫管线与内置工具集子系统

**职责**：对应上游 `packages/core/tools/`（`@deepseek-ai/dsh-tools`）及各领域工具包（`tool-fs`、`tool-fs-search`、`tool-pwsh`、`tool-jobs`、`tool-todo`、`tool-goal`、`tool-skill`、`tool-subagent`、`tool-ask-user`、`tool-present`、`eduforge-labkit`），负责管理模型可见工具的 JSON Schema 导出、执行 `tools/pre-execute -> tools/execute -> tools/post-execute` 瀑布流守卫管线，并内置 28 个标准 Agent 与物理实验工具。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`__init__.py`](__init__.py) | 已实测 | 导出 `ToolRegistry`、`ToolDefinition`、`ToolCallRequest`、`ToolExecutionResult`、`register_builtin_tools` |
| [`registry.py`](registry.py) | 已实测 | 工具注册、预设白名单过滤、OpenAI 函数调用 Schema 生成、前置/后置钩子与超时执行器绑定 |
| [`builtin_tools.py`](builtin_tools.py) | 已实测 | 一键装配 7 大类共 28 个内置工具（文件读写搜、沙箱与后台任务、Todo/Plan/Goal、技能与会话检索、Subagent 派生与 Fork、提问与交付物、6 个 `experiment_*` 物理实验工具） |

## 与上下层的关系

- **上层消费者**：[`../loop/`](../loop/README.md)（`AgentLoop` 从本注册表获取工具 Schema 并派发模型生成的 `tool_calls`）。
- **下层能力提供方**：[`../file/`](../file/README.md)、[`../sandbox/`](../sandbox/README.md)、[`../memory/`](../memory/README.md)、[`../guard/`](../guard/README.md)、[`../autonomy/`](../autonomy/README.md)、[`../skill/`](../skill/README.md)、[`../subagent/`](../subagent/README.md)、[`../interaction/`](../interaction/README.md)、[`../labkit/`](../labkit/README.md)。

## 已知的坑与纪律

1. **工具调用异常转文本返回**：工具在 `pre-execute`（如 Plan 模式拦截、未读先写拦截、审批拒绝）或 `execute` 阶段抛出的领域异常，均被封装为 `ToolExecutionResult(is_error=True, content="Error...")` 回灌给模型，保证多步工具循环不崩溃并允许模型读错自愈。
2. **双格式兼容解析**：`ToolCallRequest.from_raw` 同时兼容 OpenAI 标准嵌套 `{"id", "function": {"name", "arguments"}}` 与扁平工具字典。
