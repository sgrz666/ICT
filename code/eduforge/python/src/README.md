# src — eduforge 包源码

Python 包 `eduforge` 的全部代码，分层原则：**依赖只能从外向内**（api/worker → application → domain；infrastructure 被 application 依赖但不依赖它）。设计依据见 `plan/26.10.15_EduForge_代码级实施方案.md` §2.1。

## 模块地图

| 模块 | 职责 | 关键文件 |
|---|---|---|
| `agent/` | 执行核心、策略与执行端口 | `deepagents_runtime.py`（Deep Agents 装配与 trace）、`deepagents_runner.py`（**生产执行端口**，产出候选完成记录 `AgentRunRecord`）、`proposal_runner.py`（旧 `PlannerPort` 适配到同一条候选写入路径）、`deepagents_planner.py`（对照基线，`operations_from_trace` 不再决定交付）、`tool_registry.py`（模型可见 6 项工具）、`fake_model.py`（脚本化假模型）、[`prompts/`](eduforge/agent/prompts/README.md)（系统行为规范）、`graph.py`（四节点单轮基线）、`state.py`、`retrieval.py`、`model.py`（模型工厂）、`bootstrap.py`（`build_planner()`）、`policy.py`（服务端授权防线 + `authorize_operation`）、`services.py`。~~`tool_agent.py`~~ 已于 2026-10-16 删除 |
| `api/` | 业务 API（§6.1） | `main.py`（FastAPI 入口，含模板、实验创建、任务提交与取消、版本历史、**版本回滚**、产物下载校验；`owner_id` 由入口注入、绝不从正文接受）、`serve.py`、[`routes/`](eduforge/api/routes/README.md)（空占位包，路由实际都在 `main.py`） |
| `application/` | 用例编排 | `candidate_service.py`（**Gate A 候选业务层**：`CandidateState`/`AgentRunRecord`、canonical 内容哈希、唯一字节写法 `native_bytes`/`views_bytes`、CAS 写与冻结）、`coordinator.py`（五阶段机 planning→editing→building→validating→packaging，完成与否以 `job_events` 为准，重启后从库里的阶段恢复）、`publication.py`（原子发布）、`package_builder.py`（**Gate C §C.4 统一交付包构建**：落盘并逐字节回读、离线包内场景替换成交付字节、清单=引擎元数据+逐文件 SHA256+整包摘要，工具层与 Worker 共用）、`job_service.py`（任务提交与取消）、`experiment_service.py`（模板克隆与回滚）、`services.py`（应用层聚合导出） |
| `coding/` | 代码定制执行（§4.6） | `deep_agent.py`（受限沙箱代码定制）、`sandbox_factory.py`（OpenSandbox 工厂）、`workspace.py`（受控导出白名单校验）、`budget.py`（调用轮次与时长预算） |
| `domain/` | 核心协议与领域模型（§1.2） | `contracts.py`（DTO 与契约模型）、`models.py`（纯领域实体与聚合根）、`ports.py`（持久化与客户端端口）、`errors.py`（领域统一异常体系） |
| `entrypoints/` | 智能体入口（§6.3） | `agentarts.py`（华为云 AgentArts Runtime 运行时入口，调用同一套 `build_planner()`）、`agent_local.py`（本地 HTTP 规划服务） |
| `experiment_tools/` | 8 项实验引擎原子工具服务与协议接入 | `contracts.py`（8 项工具契约）、`service.py`（`ExperimentToolService` 核心）、`langchain_tools.py`（LangChain 工具）、`mcp_server.py`（MCP 服务端） |
| `infrastructure/` | 外部适配与基础设施 | `settings.py`（全局配置）、`catalog.py`（读引擎描述）、`clients/engine_client.py`（调 Engine Host）、`clients/agent_client.py`（调规划智能体）、`db/repositories.py`（任务/版本/产物 + 内容派生 id）/ `db/candidate_repository.py`（未发布候选工作态，CAS）/ `db/migrations/`（版本化 schema 推进）/ `db/session.py` / `db/models.py`（Postgres 仓储与连接池）、`storage/local.py` / `storage/obs.py`（本地与云端 OBS 产物持久化） |
| `research/` | 逆向研究入口（§6.4） | `rea_runner.py`（调用 REA CLI 分析仿真引擎与生成 Evidence 证据，开发研究专用） |
| `validation/` | 物理与门禁验证 | `policies.py`、`reports.py`、`scientific/optics.py`（**独立**薄透镜参考式）、`scientific/mechanics.py` / `scientific/circuits.py`（单摆与电路保留计算桩） |
| `worker/` | 任务执行进程 | `main.py`（主循环：租约 + at-least-once + 失败三分类与有限退避）、`lease.py`（租约心跳守护与执行权判定，Gate B 起已接线，心跳走池内独立连接）、`steps.py`（五阶段步骤，Gate A 起全部消费同一行持久候选，不再重放操作清单）、`run.py`（`python -m eduforge.worker.run` 入口，启动即 `apply_migrations`）、`errors.py`（TerminalError） |

## 逐文件说明（各模块自己的 README）

上表是"模块级"地图；**每个模块内部的文件级细节**（行数、导出符号、依赖与被依赖关系、实测状态）在各自 README 里：

[`eduforge/`](eduforge/README.md)（包根与全链路数据流）· [`agent/`](eduforge/agent/README.md)（另含 `prompts/` 子 README）· [`api/`](eduforge/api/README.md)（另含 `routes/` 子 README） · [`application/`](eduforge/application/README.md) · [`coding/`](eduforge/coding/README.md) · [`domain/`](eduforge/domain/README.md) · [`entrypoints/`](eduforge/entrypoints/README.md) · [`experiment_tools/`](eduforge/experiment_tools/README.md) · [`infrastructure/`](eduforge/infrastructure/README.md)（另含 `clients/`、`db/`、`storage/` 子 README）· [`research/`](eduforge/research/README.md) · [`validation/`](eduforge/validation/README.md)（另含 `scientific/` 子 README）· [`worker/`](eduforge/worker/README.md)


## "定义先行、接线未做"清单（读代码时的防误导项）

以下模块已定义并有测试覆盖，但**不在运行时链路上**：`coding/*` 全目录、`research/rea_runner.py`、`validation/scientific/mechanics.py` 与 `circuits.py`、`agent/retrieval.py`、`agent/model.py`、`infrastructure/clients/agent_client.py`、`infrastructure/storage/*`、`infrastructure/db/session.py`、`infrastructure/db/models.py`。（`worker/lease.py` 的 `LeaseManager` 曾在此列——2026-10-17 Gate B 已真正接入运行时：心跳走独立连接、`attempt`/`next_run_at` 有记账，细节见 [`worker/README.md`](eduforge/worker/README.md)。）

## 崩溃安全模型（一句话版）

任务状态只信数据库里的 `job_events`：崩掉的阶段会重跑，所以外部动作全部幂等；接管者依据事件决定从哪继续。相关测试见 [`../../tests/python/`](../../tests/python/README.md) 的 `test_gate5_recovery.py`、`test_chain_worker.py`。
