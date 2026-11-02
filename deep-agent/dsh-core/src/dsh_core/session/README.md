# session — 会话与对话处理子系统 (Session Subsystem)

**职责**：提供符合 DeepSeek Harness 官方格式版本 4（`SESSION_FORMAT_VERSION = 4`）的事件溯源会话与多轮对话处理能力。负责会话不可变元数据（`SessionHeader`）、追加式事件日志（`SessionEvent`）、大模型可见表面投影管理（`SurfaceManager`，支持 `append` 与 `replace` 历史遮蔽）、Turn/Step 智能体循环状态机、工具调用与结果的确定性因果链绑定，以及工作区安全的增量式 JSONL 磁盘持久化。

## 内容

| 文件 | 状态 | 说明 |
|---|---|---|
| [`models.py`](models.py) | 已实测 | Pydantic 数据契约，包含 `SessionEvent`、`SessionHeader`、`Turn`、`Step`、`Message`、`ToolCall`、`ToolResult` 与 `SurfaceOp` |
| [`surface.py`](surface.py) | 已实测 | 表面投影管理器 `SurfaceManager`，维护对模型可见的有序事件序号列表，支持历史区间的原位遮蔽替换 |
| [`persistence.py`](persistence.py) | 已实测 | 版本 4 规范的 JSONL 持久化引擎，提供工作区路径编码 `project_key` 与会话 ID 转义，首行保存 Header，后续行增量追加 Event |
| [`state_machine.py`](state_machine.py) | 已实测 | `Session` 容器与 `ReactLoopState` 状态机，集成收件箱（`ReactLoopInbox`）认领与工具调用因果链登记 |
| [`projection.py`](projection.py) | 已实测 | 声明式折叠投影注册表 `SessionProjectionRegistry`（内置 `sessionStats`、`turnOutline`、`turnBoundary`）与日志检索导出服务 `SessionQueryService`（对标 `dsh-session-projection` / `dsh-session-query`） |
| [`llm_client.py`](llm_client.py) | 已实测 | 模型客户端抽象协议 `BaseLlmClient`、脱网确定性测试客户端 `MockLlmClient` 及 OpenAI/DeepSeek 兼容客户端 |
| [`__init__.py`](__init__.py) | 已实测 | 子系统 API 导出入口 |

## 与上下层的关系

- **上层依赖**：被顶级包 [`../__init__.py`](../__init__.py) 统一导出；驱动智能体多轮对话循环。
- **平级协同**：
  - 内存与压缩子系统 [`../memory/`](../memory/README.md) 通过 `Session.append(..., surface_op="replace", replace_range=...)` 实现 KV-cache 友好的历史折叠。
  - 沙箱子系统 [`../sandbox/`](../sandbox/README.md) 产出的执行结果经由 `record_tool_result` 绑定到触发的 `tool/call` 上。
- **外部应用**：供教育智能体完整回放学生多轮问答、排查错误、支持中途会话断电恢复。

## 已知的坑与纪律

1. **底层日志不可变纪律**：无论表面投影如何执行 `replace` 遮蔽操作，`Session.log` 底层的追加式事件日志绝对不可删除或就地修改，必须 100% 保真以供教学评估与安全复盘。
2. **因果链强制绑定**：每一个 `tool/result` 事件必须携带 `source_event_seqs` 指向其对应的 `tool/call` 事件序号，禁止产生孤儿工具结果。
3. **序号连续性单调自增**：事件序号 `seq` 必须严格等于当前事件加入前 `log` 的长度（0-indexed 单调递增）。
