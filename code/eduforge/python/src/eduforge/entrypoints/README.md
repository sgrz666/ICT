# entrypoints — 智能体运行入口

**职责**：规划智能体在两种部署形态下的进程入口——本地开发用 HTTP 服务（供 Worker 以 HTTP 方式调用），生产迁 AgentArts 时用其运行时入口。两者都经 [`../agent/bootstrap.py`](../agent/bootstrap.py) 的 `build_planner()` 组装同一套规划器，保证"本地验证过什么，上云就跑什么"。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `__init__.py` | 1 | 入口包标记（仅注释） | — |
| `agent_local.py` | 41 | 本地开发 Agent HTTP 服务：`/plan` 收 PlanningRequest 返回 WorkOrder | `app`, `get_planner`, `set_planner` |
| `agentarts.py` | 64 | 华为云 AgentArts 运行时入口；未安装 SDK 时走兼容模式（可本地冒烟） | `app`, `handler`, `get_planner` |

## 与上下层的关系

- 依赖：[`../agent/bootstrap.py`](../agent/bootstrap.py)、[`../agent/policy.py`](../agent/policy.py)、[`../domain/contracts.py`](../domain/contracts.py)。
- 被谁用：[`../infrastructure/clients/agent_client.py`](../infrastructure/clients/agent_client.py) 的 `HttpAgentClient` 默认访问本服务的 `:8001`（该客户端当前仅测试可达；Worker 运行时是直接注入 planner，不绕 HTTP）。
- 测试：[`../../../../tests/python/test_entrypoints.py`](../../../../tests/python/test_entrypoints.py)。

## 已知的坑与纪律

- **两种入口的差异只在宿主层**：`agent_local.py` 对外是 FastAPI app，`agentarts.py` 是函数 handler；规划能力本身不出现在本目录，改规划行为去 [`../agent/`](../agent/README.md)。
- `agentarts.py` 的"兼容模式"是给未装 SDK 的本地环境用的——上真云时以 AgentArts 文档为准，别把兼容模式当生产形态。
- 端口 `:8001` 是约定值，改端口要同步 `agent_client.py` 的默认值与部署脚本。
