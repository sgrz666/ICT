# clients — HTTP 客户端（Engine Host / Agent）

**职责**：把外部服务封装成类型化 HTTP 客户端。两个文件的地位截然不同：`engine_client.py` 是**运行时要件**（editing 阶段唯一引擎调用点），`agent_client.py` 是**仅测试可达的预留件**（Worker 运行时直接注入 planner，不绕 HTTP）。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `engine_client.py` | 83 | Engine Host HTTP 客户端：`template`/`apply`（`POST /adapters/ray_optics/...`）、`sharpest_screen` 取实测像面 | `EngineClient`, `EditRejected`, `EngineUnavailable`, `sharpest_screen` |
| `agent_client.py` | 45 | Agent 规划客户端：本地直调/HTTP 两种实现（`AgentPlannerPort`） | `LocalAgentClient`, `HttpAgentClient` |

## 与上下层的关系

- 依赖：仅 `httpx`（engine_client）与 [`../../agent/bootstrap.py`](../../agent/README.md)、[`../../domain/`](../../domain/README.md)（agent_client）。
- 被谁用：[`../../worker/steps.py`](../../worker/steps.py) 在 editing 阶段构造 `EngineClient(engine_url)`；`sharpest_screen` 与 `agent_client` 仅测试引用。
- 对端：Engine Host 的适配器路由见 [`../../../../../services/engine-host/src/README.md`](../../../../../services/engine-host/src/README.md)。

## 已知的坑与纪律

- 错误语义要分清：上游**拒绝修改**（422 `NATIVE_REJECTED`）→ 抛 `EditRejected`（业务语义，不重试）；**连不上/5xx** → `EngineUnavailable`（可重试）。别把两者混成一个异常。
- `sharpest_screen` 是测试用来核对"实测像面位置"的，主链路里 validating 阶段用的是 Engine Host 返回的 `measurement` 字段。
- `agent_client.py` 接进运行时 = 架构变更（规划从进程内调用变成服务调用），需要同步改 `worker/run.py` 的组装方式并补部署脚本。
