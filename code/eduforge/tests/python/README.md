# python — pytest 用例

EduForge Python 侧的全部测试：**23 个文件（21 个 `test_*.py` + `conftest.py` + `_regex_baseline.py` 对照组夹具）**，收集 125 项、124 通过、1 SKIPPED（计数唯一来源仍是 [`../../catalog/engines/ray-optics.yaml`](../../catalog/engines/ray-optics.yaml) 的 `test_totals`；SKIPPED 是无 key 的真模型用例）。跑法：工程根 `uv run pytest`（`-q`）。这里的共同风格是**起真东西**：真 Postgres（pgserver）、真 uvicorn、真 Worker 子进程、真浏览器；只有规划在部分用例里由命令行注入固定提案，那种绿不代表模型能力。

> 建库统一走 `infrastructure/db/migrations.apply_migrations`（2026-10-17 Gate A 起），夹具不再各跑一份 `JOBS_DDL`；清表时 `jobs` 行删除会级联掉 `experiment_candidates`。

## 文件地图

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `conftest.py` | 70 | 夹具（库、应用、临时环境） |
| `test_agent_tools_acceptance.py` | 631 | 8 项原子工具的端到端验收与**门禁负向用例**：真实导入、多参数与测量表格生效、连续编辑父子链（先构建核验再原子发布）、离线包 manifest 逐文件对上磁盘、并发 RevisionConflict、超量程请求如实被拒（不得偷换值）、过期验证结论不得授权发布、无执行上下文不得回报「已发布」。边界用例 3（u=f 准直与 u<f 虚像）自 §C.2 起**必须 passed** 并核对实测交点与 `|slope| ≤ 2σ`，不再接受"测不出来所以 inconclusive 也算对" |
| `test_gate2_protocol.py` | 126 | 修改协议：pydantic 校验、阈值（清晰 ≥0.8 / 弥散 ≤0.4 / 之间不可判）与控制组 |
| `test_gate5_api_chain.py` | 242 | §6.1 使用链：选模板→建实验→提交(幂等)→查任务→取消→查实验→下载产物；产物完整性（哈希锁定、缺失 404、不符 500、`storage_key` 越界 403） |
| `test_gate5_cancel.py` | 143 | 取消语义（已成功不回滚、活跃任务状态一致性） |
| `test_gate5_lease.py` | 245 | 租约领取/续租/抢占（`FOR UPDATE SKIP LOCKED` 语义） |
| `test_gate5_recovery.py` | 111 | 崩溃恢复（第二个 Worker 从持久化事实重建并完成） |
| `test_gate5_rollback.py` | 164 | §6.1 版本回滚：原子事务迁回目标版本保留历史、跨实验版本非法拦截、活跃任务冲突防御（409） |
| `test_gate6_planning.py` | 152 | 规划图与策略链（桩模型，无需 DeepSeek 密钥） |
| `test_planner_port.py` | 132 | 规划端口契约（`GraphPlanner` 与 `planner_from_env` 行为） |
| `test_entrypoints.py` | 116 | §6.3 智能体入口：华为云 AgentArts 运行时契约、本地 HTTP 规划与策略错误码映射 |
| `test_benchmarks.py` | 43 | §7.4 基准评测回归：区分 screening / direct / agent_graph 三种评测，无 key 显式 SKIPPED 杜绝规则伪充 |
| `test_plan_architecture_alignment.py` | 205 | 方案全貌架构对齐：验证 domain/models/errors、agent/retrieval、coding/workspace/budget、worker/lease、research/rea_runner、infrastructure 各模块自洽性 |
| `test_chain_worker.py` | 411 | 生产链路：API 提交→Worker 五阶段→原子发布→产物字节级校验；策略拒绝与验证不过都落 `failed` 且不动 head；支持复合操作（改焦距+设置记录表）。**物理边界两条凭实测发布**（2026-10-17 §C.2 补量具后）：`test_chain_far_virtual_image_publishes_on_measured_divergence`（f=40 虚像，实测交点 −119.6cm 对上参考 −120）与 `test_chain_parallel_beam_publishes_on_measured_parallelism`（u=f，斜率与零不可区分）；`test_validation_failure_blocks_publish`（f=5，交付屏上不成像）仍必须失败。候选版本与产物 id 改为**读 `jobs.candidate_revision_id`**（内容派生 id 由生产计算，用例不自己拼） |
| `test_gate_b_execution_rights.py` | 599 | **Gate B 执行权与归属（2026-10-17 新增，11 项）**：心跳续租并带控制组（没池就会被抢走）、租约过期不得自续、丢权后新写入与发布都被拒、取消回报 `JOB_CANCELLED`、`attempt` 递增 + `retry_later` 退避 + `MAX_ATTEMPTS_EXCEEDED`、并发追加事件序号唯一、发布重放核对字节与归属、跨 owner 读改下载一律 404、关闭开发身份后无凭据 401、双 Worker 只产生一份交付 |
| `test_gate_a_candidate.py` | 491 | **Gate A 统一候选执行链（2026-10-17 新增，10 项）**：旧库能升级到 `experiment_candidates` 且迁移幂等、一个 job 只有一行候选、新建 service 实例读回同一份未发布内容、先改 A 再改 B 只能交付 B（A 的绿灯当场清空）、重复构建/发布不产生第二候选或重复产物、换绑实验被拒、两个 service 并发写后者被 CAS 拒绝、纯视图（只开记录表）任务跑通且基线未被误判改写、脚本模型经 `make_worker` 全链交付且「候选字节 = 落盘字节 = 下载哈希」逐字节成立、纯视图任务走完整五阶段不被误判为基线被改 |
| `test_publish_chain.py` | 305 | 发布链（原子性、版本可恢复） |
| `test_contracts_surface.py` | 132 | §6.2 守卫：每个业务接口 2xx 都必须指向具名 DTO（生成物落后于后端即红） |
| `test_teacher_web_e2e.py` | 304 | 切片 8 金路径：真浏览器驱动教师前端走完整使用链（含版本回滚、下载文件本地重算哈希校验）；head 与产物 id 断言改为对照 `jobs.candidate_revision_id` 与 `artifact_id_for(job, "native", sha256)` |
| `test_deepagents_runtime.py` | 249 | Deep Agents 循环与门禁（**脚本化假模型**，不触网）：多轮往返确实发生、`build_package`/`publish_revision` 不在模型可见集且模型可见 schema 无身份字段、观察驱动写入值、越界请求以失败被观察而非偷偷换值、正则对照组的措辞脆弱性 |
| `test_deepagents_real_model.py` | 123 | 真实模型（`deepseek-flash`）自主完成「焦距 15 + 物距 30 + 记录表」并落 Tool Trace 报告；**无 key 时显式 SKIPPED**，不拿规则冒充模型 |
| `test_single_publish_path.py` | 68 | 结构守卫：带租约证明的发布插入只存在于持久层一条事务、工具层发布不再自写 SQL、DDL 单一来源、回滚不改写既有修订 |
| `_regex_baseline.py` | 51 | 对照组夹具（非用例）：从 `main` 分支原样取回已删除的正则意图解析器，用于「模型 vs 模式匹配」的可执行比较 |

## 测试 → 被测代码（主要映射）

| 测试 | 主要打到的源码 |
|---|---|
| `test_agent_tools_acceptance` | [`experiment_tools/`](../../python/src/eduforge/experiment_tools/README.md)（8 项工具服务 + 策略清单 + 发布委托） |
| `test_deepagents_runtime` / `test_deepagents_real_model` | [`agent/`](../../python/src/eduforge/agent/README.md)（`deepagents_runtime`、`tool_registry`、`fake_model`、`model`）、[`experiment_tools/`](../../python/src/eduforge/experiment_tools/README.md) |
| `test_single_publish_path` | [`infrastructure/db/repositories.py`](../../python/src/eduforge/infrastructure/README.md)、[`application/`](../../python/src/eduforge/application/README.md)、[`experiment_tools/service.py`](../../python/src/eduforge/experiment_tools/README.md) |
| `test_chain_worker` / `test_publish_chain` | [`worker/`](../../python/src/eduforge/worker/README.md)（五阶段）、[`application/`](../../python/src/eduforge/application/README.md)（发布门禁）、[`infrastructure/db/`](../../python/src/eduforge/infrastructure/README.md) |
| `test_gate5_*` | [`api/`](../../python/src/eduforge/api/README.md)、[`application/coordinator.py`](../../python/src/eduforge/application/README.md)、`repositories.py` |
| `test_gate6_planning` / `test_planner_port` | [`agent/`](../../python/src/eduforge/agent/README.md)（图、策略、端口） |
| `test_entrypoints` | [`entrypoints/`](../../python/src/eduforge/entrypoints/README.md) |
| `test_teacher_web_e2e` | 真进程 `worker.run` + `api.serve` + 浏览器（GATE-8 侧） |
| `test_contracts_surface` | [`api/main.py`](../../python/src/eduforge/api/README.md) 的 response_model |
| `test_plan_architecture_alignment` | 全包（含"已定义未接入"预留模块） |


## 与其他层的关系

- 协议与实现的对应：被测代码在 [`../../python/src/`](../../python/src/README.md)；引用的事实基准在 [`../../catalog/engines/ray-optics.yaml`](../../catalog/engines/ray-optics.yaml)。
- 与 TS 侧用例的分界见 [`../README.md`](../README.md)。
