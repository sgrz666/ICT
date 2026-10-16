# eduforge — Python 包根（包名 `eduforge`）

**职责**：EduForge 的 Python 包本体，承载「教师提需求 → 规划 → 执行 → 验证 → 发布」全链路的服务端逻辑。与 TypeScript 侧（`engine-host` 仿真宿主、`teacher-web` 教师前端）通过 HTTP 契约协作；本包不直接跑仿真，仿真一律经 Engine Host 转发给上游 Ray Optics。

## 内容

包根只有 `__init__.py`（空包标记）与 11 个子包：

| 子包 | 一句话职责 | 关键入口 | 逐文件细节 |
|---|---|---|---|
| [`agent/`](agent/README.md) | 规划智能体：LangGraph 四节点图 + 工具调用循环 + 服务端授权 | `bootstrap.build_planner` | agent/README.md |
| [`api/`](api/README.md) | FastAPI 业务接口（模板/实验/任务/产物） | `main.create_app` | api/README.md |
| [`application/`](application/README.md) | 应用服务层：实验版本、任务生命周期、发布门禁、阶段机 | `coordinator.Coordinator` | application/README.md |
| [`coding/`](coding/README.md) | 代码定制沙箱与执行预算（切片 7 预留，**未接入运行时**） | `deep_agent.customize` | coding/README.md |
| [`domain/`](domain/README.md) | 纯净核心：数据契约（Pydantic）、异常、实体、端口协议 | `contracts.EditProposal` | domain/README.md |
| [`entrypoints/`](entrypoints/README.md) | 智能体运行入口（本地 HTTP / AgentArts 运行时） | `agent_local.app` | entrypoints/README.md |
| [`experiment_tools/`](experiment_tools/README.md) | **实验引擎工具服务层**：8 项原子工具，供 LangGraph / Deep Agents / MCP Client 调用 | `service.ExperimentToolService` | experiment_tools/README.md |
| [`experiment_tools/`](experiment_tools/README.md) | 8 项实验引擎原子工具服务与 LangChain/MCP 接入 | `service.ExperimentToolService` | experiment_tools/README.md |
| [`infrastructure/`](infrastructure/README.md) | 基础设施：清单读取、数据库仓储、引擎/智能体客户端、存储 | `catalog.load_template` | infrastructure/README.md |
| [`research/`](research/README.md) | REA 逆向分析运行器（开发期工具，**不进入教师业务链路**） | `rea_runner.REARunner` | research/README.md |
| [`validation/`](validation/README.md) | 验证与发布门禁：检查项汇总 + 独立科学参考式 | `policies.build_report` | validation/README.md |
| [`worker/`](worker/README.md) | 任务执行：五阶段流水线 + 租约 + 进程入口 | `steps.make_worker` | worker/README.md |


## 一次请求的数据流（教师提需求 → 交付实验包）

以下为真实代码调用链（config route；`code` route 在规划阶段即被拒）：

1. `POST /experiments` → [`api/main.py`](api/main.py) → [`application/experiment_service.py`](application/experiment_service.py) `create_from_template`：读模板 `native.json`，落库实验 + 基础版本。
2. `POST /jobs`（带 `Idempotency-Key`）→ [`application/job_service.py`](application/job_service.py) → [`infrastructure/db/repositories.py`](infrastructure/db/repositories.py) `create_job`：`request_hash` 幂等去重，落 `queued`。
3. Worker 进程（[`worker/run.py`](worker/run.py)）循环 `Worker.run_once`（[`worker/main.py`](worker/main.py)）；`claim` 用 `FOR UPDATE SKIP LOCKED` 原子领取拿 `lease_token`；[`worker/steps.py`](worker/steps.py) `make_worker` 组装 `Chain`。
4. [`application/coordinator.py`](application/coordinator.py) 按 `STAGES` 推进，依据 `job_events.stage_done` 断点恢复。
5. **planning**：`Chain.planning` → `planner.plan`（[`agent/planners.py`](agent/planners.py) `GraphPlanner` → [`agent/graph.py`](agent/graph.py) 四节点，`draft` 节点 HTTP 调 DeepSeek）→ [`agent/policy.py`](agent/policy.py) `authorize` 二次校验生成 `WorkOrder`。
6. **editing**：`Chain._apply` → [`infrastructure/clients/engine_client.py`](infrastructure/clients/engine_client.py) `EngineClient.apply` → HTTP 到 Engine Host（Node）改上游场景并仿真。
7. **building**：`Chain.building` 序列化候选场景写 `artifact_dir/revisions/{candidate}/native.json`，算 sha256。
8. **validating**：`Chain.validating` → [`validation/policies.py`](validation/policies.py) `build_report`（科学对照调 [`validation/scientific/optics.py`](validation/scientific/optics.py)）→ [`application/publication.py`](application/publication.py) `record_report`。
9. **packaging**：`verdict=passed` 才 `Publisher.publish` → `JobRepository.publish` 单事务发布版本、登记产物、前移 head、置 `succeeded`。
10. `GET /artifacts/{id}/download`：读文件 + path 越界 403 校验 + **重算 sha256 与库比对**，随 `x-content-sha256` 返回。

## 与上下层的关系

- 上层：工程根 [`python/`](../../README.md) 管理依赖与 pytest 配置；包内入口只有两个进程级脚本——[`api/serve.py`](api/serve.py)（uvicorn 服务）与 [`worker/run.py`](worker/run.py)（Worker 循环）。
- 横向：对 Engine Host 的唯一调用点在 [`infrastructure/clients/engine_client.py`](infrastructure/clients/engine_client.py)（HTTP，`EDUFORGE_ENGINE_URL`）。
- 引用侧：测试套件在 [`../../../tests/python/`](../../../tests/python/README.md)；引擎描述与模板在 [`../../../catalog/`](../../../catalog/README.md)；验证证据在 [`../../../../../output/eduforge/reports/`](../../../../../output/eduforge/reports/README.md)。

## 已知的坑与纪律

- **"已定义但未接入运行时"的模块**（仅有测试可达，读代码时不要当成主链路）：`coding/*` 全目录、`research/rea_runner.py`、`validation/scientific/mechanics.py`、`validation/scientific/circuits.py`、`agent/retrieval.py`、`agent/model.py`、`infrastructure/clients/agent_client.py`、`infrastructure/storage/*`、`infrastructure/db/session.py`、`infrastructure/db/models.py`、`worker/lease.py` 的 `LeaseManager`（运行时靠 `repo.claim`/`lease_token`，非此守护器）。
- **`code` route 当前不执行**：[`worker/steps.py`](worker/steps.py) 在 planning 阶段对 `route=='code'` 直接判 `CODE_ROUTE_NOT_EXECUTED`。
- **`api/routes/` 未拆分**：实际只有 `__init__.py`，全部路由集中在 [`api/main.py`](api/main.py)。
- **无 DeepSeek key 时 Worker 拒绝启动**（key 解析见 [`infrastructure/settings.py`](infrastructure/README.md) 的 `get_deepseek_api_key()`；`--planner-static-focal` 仅用于本地链路验证，不构成真实规划证据）。
- **数据契约的 `extra=forbid`**：`SetParameter/SetView/EditProposal/WorkOrder/PlannerRequest/CreateJobRequest` 全部拒绝多余字段，改协议先在 [`domain/contracts.py`](domain/contracts.py) 动。
