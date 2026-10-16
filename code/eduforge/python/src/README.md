# src — eduforge 包源码

Python 包 `eduforge` 的全部代码，分层原则：**依赖只能从外向内**（api/worker → application → domain；infrastructure 被 application 依赖但不依赖它）。设计依据见 `plan/26.10.15_EduForge_代码级实施方案.md` §2.1。

## 模块地图

| 模块 | 职责 | 关键文件 |
|---|---|---|
| `agent/` | LangGraph 规划图与策略 | `graph.py`（图编排）、`state.py`（规划状态机）、`retrieval.py`（教学依据与参数检索）、`model.py`（DeepSeek 接入）、`bootstrap.py`（`build_planner()` 标准构建入口）、`policy.py`（策略拒绝，如路由不支持）、`services.py`（桩模型与业务调度） |
| `api/` | 业务 API（§6.1） | `main.py`（FastAPI 入口，含模板、实验创建、任务提交与取消、版本历史、**版本回滚**、产物下载校验；`owner_id` 由入口注入、绝不从正文接受）、`serve.py`、`routes/` |
| `application/` | 用例编排 | `coordinator.py`（五阶段机 planning→editing→building→validating→packaging，完成与否以 `job_events` 为准，重启后从库里的阶段恢复）、`publication.py`（原子发布）、`job_service.py`（任务提交与取消）、`experiment_service.py`（模板克隆与回滚）、`services.py`（应用层聚合导出） |
| `coding/` | 代码定制执行（§4.6） | `deep_agent.py`（受限沙箱代码定制）、`sandbox_factory.py`（OpenSandbox 工厂）、`workspace.py`（受控导出白名单校验）、`budget.py`（调用轮次与时长预算） |
| `domain/` | 核心协议与领域模型（§1.2） | `contracts.py`（DTO 与契约模型）、`models.py`（纯领域实体与聚合根）、`ports.py`（持久化与客户端端口）、`errors.py`（领域统一异常体系） |
| `entrypoints/` | 智能体入口（§6.3） | `agentarts.py`（华为云 AgentArts Runtime 运行时入口，调用同一套 `build_planner()`）、`agent_local.py`（本地 HTTP 规划服务） |
| `infrastructure/` | 外部适配与基础设施 | `settings.py`（全局配置）、`catalog.py`（读引擎描述）、`clients/engine_client.py`（调 Engine Host）、`clients/agent_client.py`（调规划智能体）、`db/repositories.py` / `db/session.py` / `db/models.py`（Postgres 仓储与连接池）、`storage/local.py` / `storage/obs.py`（本地与云端 OBS 产物持久化） |
| `research/` | 逆向研究入口（§6.4） | `rea_runner.py`（调用 REA CLI 分析仿真引擎与生成 Evidence 证据，开发研究专用） |
| `validation/` | 物理与门禁验证 | `policies.py`、`reports.py`、`scientific/optics.py`（**独立**薄透镜参考式）、`scientific/mechanics.py` / `scientific/circuits.py`（单摆与电路保留计算桩） |
| `worker/` | 任务执行进程 | `main.py`（主循环：租约 + at-least-once，阶段必须幂等）、`lease.py`（租约心跳守护与执行权校验）、`steps.py`（五阶段步骤）、`run.py`（`python -m eduforge.worker.run` 入口）、`errors.py`（TerminalError） |

## 崩溃安全模型（一句话版）

任务状态只信数据库里的 `job_events`：崩掉的阶段会重跑，所以外部动作全部幂等；接管者依据事件决定从哪继续。相关测试见 [`../../tests/python/`](../../tests/python/README.md) 的 `test_gate5_recovery.py`、`test_chain_worker.py`。
