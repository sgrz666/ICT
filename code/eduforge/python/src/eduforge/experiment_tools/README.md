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
| `open_experiment` | 是 | `owner_id` **不再是入参**（改由 `JobContext` 注入并校验归属）；job 绑定了实验就只能开那个实验；取回的是**本 job 绑定的候选行**（`experiment_candidates`），已有未发布内容时不覆盖、直接续用；换绑实验或基线版本被拒 |
| `inspect_scene` | 是 | 返回真实场景读数 + 薄透镜独立参考值；缓存没有就从候选行重建（重启后可继续） |
| `apply_scene_patch` | 是 | 每条 edit 先过 `policy.authorize_operation`（未登记 → `PARAMETER_NOT_REGISTERED`，超量程 → `VALUE_OUT_OF_RANGE`）；引擎拒绝改为抛 `ConflictError`，不再返回 `status="rejected: …"` 字符串；改完**写穿候选**（`state_version` CAS），旧验证结论当场作废；写不进去就报失败，不回报成功 |
| `configure_teaching_views` | 是 | 视图必须在模板 `views` 清单内，否则 `VIEW_NOT_REGISTERED`；同样写穿候选、同样令验证作废 |
| `run_validation` | 是 | 强制引擎往返；报告当场写 `validation_reports`，并把 `validation_id` + `content_hash` **绑到候选行**上（内容再变即失配，旧绿灯不作数） |
| `build_package` | **否（后端）** | 先 `freeze()` 候选，再按**候选内容哈希**派生版本与产物 id（`revision_id_for` / `artifact_id_for`，重跑幂等、改内容才成新版本）；落盘字节由 `application/candidate_service.py` 的 `native_bytes`/`views_bytes` 唯一决定；离线包整目录出 `manifest.json` 逐文件哈希 |
| `publish_revision` | **否（后端）** | 必须有 `JobContext` + 库连接；走 `application/publication.py` → `JobRepository.publish`；发布前用库里的候选重算版本 id，与构建时登记的不一致就拒（防「构建一份、发布另一份」）；`close_job=False` 支持同一 job 连续提交多个版本，发布后 `rebase` 候选基线 |

### 模块文件清单

- [`__init__.py`](__init__.py)（48 行）: 模块入口导出；
- [`contracts.py`](contracts.py)（165 行）: 契约模型（全部继承 `domain/contracts.py` 的 `Contract`，`extra="forbid"`）+ `JobContext`；
- [`service.py`](service.py)（851 行）: `ExperimentToolService` 核心实现——8 项工具 + 候选写穿（`self.candidates`）+ 冻结/发布衔接；
- [`langchain_tools.py`](langchain_tools.py)（136 行）: LangChain `StructuredTool` 封装 `get_experiment_tools`（8 项全量，供后端与 MCP 使用）；
- [`mcp_server.py`](mcp_server.py)（163 行）: 手写 stdlib JSON-RPC over stdio。**尚未通过 MCP 合规**：只处理 `initialize`/`tools/list`/`tools/call`，对 `notifications/initialized` 回 `-32601`，`protocolVersion` 硬编码不协商，无 `ping`，解析失败不响应（会挂死客户端），`run_mcp_stdio` 零调用者、未实测。

## 3. 与上下层的关系

- **上层使用者**:
  - [`eduforge.agent.tool_registry`](../agent/tool_registry.py) → [`deepagents_runtime`](../agent/deepagents_runtime.py) / [`deepagents_planner`](../agent/deepagents_planner.py)：只暴露 6 项，`build_package`/`publish_revision` 不在模型可见集；
  - [`eduforge.worker.steps`](../worker/steps.py)：Gate A 起**改为调用本层**——`Chain.building` 调 `build_package`、`Chain.validating` 调 `run_validation`、`Chain.editing/packaging` 读同一行候选。工具层与 Worker 不再是两份操作语义（`Chain._apply` 的重放路径已删除）；
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
5. **验证结论会过期**：`content_hash` = sha256(canonical JSON of native + views)，实现只在 [`../application/candidate_service.py`](../application/candidate_service.py) 一处。浮点走 12 位有效数字、整数值浮点归一成整数——`jsonb` 会把 `150` 读回 int、把 `15.0` 读回 float，不归一就会给同一份场景算出两个哈希。新增写操作**不需要**记得清报告；
6. **`_sessions` 只是缓存**（2026-10-16 Gate A 起）：未发布工作态的真相在 `experiment_candidates`，新建一个 service 实例（等价于进程重启或接管者）能读回同一行、同一 `content_hash`。没有 `JobContext` 时退化为纯内存（不落库，因为无从确定归属），那条路径不能作为持久化证据；
7. **本层与 Worker 步骤已合成一条**：`worker/steps.py` 的 building/validating 直接调这里；`test_single_publish_path.py` 钉「发布事务只有一条」，`test_gate_a_candidate.py` 钉「候选行只有一行、交付字节等于候选字节」。仍存的分歧是**离线包构建**：只有工具路径会出 `offline_package`，Worker 不建包（统一 Package Builder 属 Gate C）；
8. `close_job` 由调用方（后端）决定，不由模型决定——一个 job 可以连续提交多个版本，终态只在最后一次落。
