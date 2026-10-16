# experiment_tools — 实验引擎工具服务层

## 1. 职责

将底层仿真引擎（Engine Host）、模板目录（`catalog/templates/`）与数据库存储编排为 8 项标准原子工具，
作为 Agent 执行框架（Deep Agents / LangChain / MCP Client）的操作端口。
验证不是文本比对：`run_validation` 强制打一次真实引擎，判据带 `observed` 与 `expected`。

**本轮（2026-10-16）起这一层才真正可信**：写操作全部经过服务端签发的 `JobContext` 与策略清单，
验证结论绑定内容指纹，发布委托持久层的四道闸门事务。在此之前它是一条**不经授权**的写路径。

## 2. 内容（8 项工具与文件清单）

### 8 项原子工具

| 工具 | 给主 Agent？ | 本轮生效的约束 |
|---|---|---|
| `search_experiments` | 是 | 模板清单 + `experiments` 行；无登记能力就返回空，不静默换成凸透镜 |
| `open_experiment` | 是 | `owner_id` **不再是入参**（改由 `JobContext` 注入并校验归属）；job 绑定了实验就只能开那个实验 |
| `inspect_scene` | 是 | 返回真实场景读数 + 薄透镜独立参考值 |
| `apply_scene_patch` | 是 | 每条 edit 先过 `policy.authorize_operation`（未登记 → `PARAMETER_NOT_REGISTERED`，超量程 → `VALUE_OUT_OF_RANGE`）；引擎拒绝改为抛 `ConflictError`，不再返回 `status="rejected: …"` 字符串；改完使验证结论作废 |
| `configure_teaching_views` | 是 | 视图必须在模板 `views` 清单内，否则 `VIEW_NOT_REGISTERED`；改完使验证结论作废 |
| `run_validation` | 是 | 强制引擎往返；结论 + 内容指纹一起存，并**当场写入 `validation_reports`** |
| `build_package` | **否（后端）** | 候选与产物 id 由 `derived_id(job_id, …)` 派生（重跑幂等）；离线包整目录出 `manifest.json` 逐文件哈希 |
| `publish_revision` | **否（后端）** | 必须有 `JobContext` + 库连接；走 `application/publication.py` → `JobRepository.publish`；`close_job=False` 支持同一 job 连续提交多个版本 |

### 模块文件清单

- [`__init__.py`](__init__.py)（48 行）: 模块入口导出；
- [`contracts.py`](contracts.py)（165 行）: 契约模型（全部继承 `domain/contracts.py` 的 `Contract`，`extra="forbid"`）+ `JobContext`；
- [`service.py`](service.py)（770 行）: `ExperimentToolService` 核心实现；
- [`langchain_tools.py`](langchain_tools.py)（136 行）: LangChain `StructuredTool` 封装 `get_experiment_tools`（8 项全量，供后端与 MCP 使用）；
- [`mcp_server.py`](mcp_server.py)（163 行）: 手写 stdlib JSON-RPC over stdio。**尚未通过 MCP 合规**：只处理 `initialize`/`tools/list`/`tools/call`，对 `notifications/initialized` 回 `-32601`，`protocolVersion` 硬编码不协商，无 `ping`，解析失败不响应（会挂死客户端），`run_mcp_stdio` 零调用者、未实测。

## 3. 与上下层的关系

- **上层使用者**:
  - [`eduforge.agent.tool_registry`](../agent/tool_registry.py) → [`deepagents_runtime`](../agent/deepagents_runtime.py) / [`deepagents_planner`](../agent/deepagents_planner.py)：只暴露 6 项，`build_package`/`publish_revision` 不在模型可见集；
  - [`eduforge.worker.steps`](../worker/steps.py)：五阶段仍自己走引擎与发布事务，**尚未改为调用本层**（两套实现并存是本轮已知未完成项，见下）；
  - 外部 MCP 客户端（未实测）；Web API 与验收测试。
- **下层协作者**:
  - [`eduforge.infrastructure.clients.engine_client`](../infrastructure/clients/engine_client.py): HTTP 驱动 Node.js Engine Host 仿真与离线包打包；
  - [`eduforge.validation.policies`](../validation/policies.py): 物理规则与双轨光学校验；
  - [`eduforge.application.publication`](../application/publication.py) → [`repositories`](../infrastructure/db/repositories.py): 唯一的发布事务；
  - [`eduforge.agent.policy`](../agent/policy.py): `authorize_operation`，与 Worker 共用同一套清单判据。

## 4. 已知的坑与纪律

1. **版本连续编辑链**: 第二次修改（如连续将物距从 30cm 改为 20cm）必须以第一次发布的版本作为 `base_revision`（乐观并发前置条件，库里用 `FOR UPDATE` 核对），不得死锁或使用初始种子版本覆盖；
2. **教学视图数据累加**: 测量记录表在连续实验过程中应当保留前次测量记录并追加新记录，不可直接覆盖清空；
3. **真实光路验证**: 验证必须核验场景内实际元件参数与成像光斑物理二阶矩，杜绝仅做静态文本比对；
4. **模型不得自报身份与版本**: `owner_id`/`job_id`/`lease_token` 只来自 `JobContext`；`Contract` 的 `extra="forbid"` 就是为了让模型多吐一个身份字段直接失败；
5. **验证结论会过期**：`_working_digest()` = sha256(native + views_config)，指纹一变旧报告一律不作数。新增写操作**不需要**记得清报告——这正是不把「到处清标志」当机制的原因；
6. **`_sessions` 仍是进程内状态**：未发布的编辑（改后的 native、视图配置、engine 结果）重启即丢；已发布版本安全（`open_experiment` 从 `experiment_revisions.native_data` 读回）。彻底外置到库里仍是 pending；
7. **本层与 Worker 步骤是两份实现**：`worker/steps.py` 自己走引擎 + `Publisher`，本层是另一条工具面。`test_single_publish_path.py` 钉住了「发布事务只有一条」，但「操作语义只有一份」还没做到；
8. `close_job` 由调用方（后端）决定，不由模型决定——一个 job 可以连续提交多个版本，终态只在最后一次落。
