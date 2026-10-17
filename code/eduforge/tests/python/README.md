# python — pytest 用例

EduForge Python 侧的全部测试：**24 个文件（22 个 `test_*.py` + `conftest.py` + `_regex_baseline.py` 对照组夹具）**，收集 136 项、135 通过、1 SKIPPED（2026-10-17 17:45 实测）（计数唯一来源仍是 [`../../catalog/engines/ray-optics.yaml`](../../catalog/engines/ray-optics.yaml) 的 `test_totals`；SKIPPED 是无 key 的真模型用例）。跑法：工程根 `uv run pytest`（`-q`）。这里的共同风格是**起真东西**：真 Postgres（pgserver）、真 uvicorn、真 Worker 子进程、真浏览器；只有规划在部分用例里由命令行注入固定提案，那种绿不代表模型能力。

**临时目录必须自己收尾**：各文件各自 `pgserver.get_server(mkdtemp(...), cleanup_mode=None)` 起一次性 Postgres，Windows 上 `stop()` 还常慢一拍；历史上每次全量都在 `%TEMP%` 留下一堆数据簇与产物目录（2026-10-17 一天内堆到上千个，用户因此抱怨磁盘）。清扫由 `conftest.py` 兜底，但新增夹具时请自己在收尾删目录，别把兜底当借口。

> 建库统一走 `infrastructure/db/migrations.apply_migrations`（2026-10-17 Gate A 起），夹具不再各跑一份 `JOBS_DDL`；清表时 `jobs` 行删除会级联掉 `experiment_candidates`。

## 文件地图

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `conftest.py` | 128 | 共享夹具：真起 Engine Host 子进程（`engine_url`，端口随机、缺 dist 先编译）＋会话级临时目录清扫 `_sweep_own_temp_dirs`（开场清 30 分钟以上的历史遗留 `eduforge-*`，收尾清本轮新建的；删不掉就 warn，不假装干净） |
| `test_agent_tools_acceptance.py` | 641 | 8 项原子工具的端到端验收与**门禁负向用例**：真实导入、多参数与测量表格生效、连续编辑父子链（先构建核验再原子发布）、离线包 manifest 逐文件对上磁盘、并发 RevisionConflict、超量程请求如实被拒（不得偷换值）、过期验证结论不得授权发布、无执行上下文不得回报「已发布」。边界用例 3（u=f 准直与 u<f 虚像）自 §C.2 起**必须 passed** 并核对实测交点与 `|slope| ≤ 2σ`，不再接受"测不出来所以 inconclusive 也算对" |
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
| `test_chain_worker.py` | 442 | 生产链路：API 提交→Worker 五阶段→原子发布→产物字节级校验；策略拒绝与验证不过都落 `failed` 且不动 head；支持复合操作（改焦距+设置记录表）。**物理边界两条凭实测发布**（2026-10-17 §C.2 补量具后）：`test_chain_far_virtual_image_publishes_on_measured_divergence`（f=40 虚像，实测交点 −119.6cm 对上参考 −120）与 `test_chain_parallel_beam_publishes_on_measured_parallelism`（u=f，斜率与零不可区分）；`test_validation_failure_blocks_publish`（f=5，交付屏上不成像）仍必须失败。候选版本与产物 id 改为**读 `jobs.candidate_revision_id`**（内容派生 id 由生产计算，用例不自己拼）。§C.4 起一次发布登记**两份**产物（`native.json` + 离线包 `manifest.json`），用例同时核对包内场景字节 = 交付字节、清单里引擎交付元数据仍在、`package_sha256` 可由逐文件表重算 |
| `test_gate_b_execution_rights.py` | 631 | **Gate B 执行权与归属（2026-10-17 新增，12 项）**：心跳续租并带控制组（没池就会被抢走）、租约过期不得自续、丢权后新写入与发布都被拒、取消回报 `JOB_CANCELLED`、`attempt` 递增 + `retry_later` 退避 + `MAX_ATTEMPTS_EXCEEDED`、并发追加事件序号唯一、发布重放核对字节与归属、跨 owner 读改下载一律 404、关闭开发身份后无凭据 401、双 Worker 只产生一份交付；**并发续租必须串行**（20 次 `beat()` 同时打在一条守护连接上，没有锁就当场抛 asyncpg `InterfaceError`，全量跑时真抓到过一次） |
| `test_gate_a_candidate.py` | 491 | **Gate A 统一候选执行链（2026-10-17 新增，10 项）**：旧库能升级到 `experiment_candidates` 且迁移幂等、一个 job 只有一行候选、新建 service 实例读回同一份未发布内容、先改 A 再改 B 只能交付 B（A 的绿灯当场清空）、重复构建/发布不产生第二候选或重复产物、换绑实验被拒、两个 service 并发写后者被 CAS 拒绝、纯视图（只开记录表）任务跑通且基线未被误判改写、脚本模型经 `make_worker` 全链交付且「候选字节 = 落盘字节 = 下载哈希」逐字节成立、纯视图任务走完整五阶段不被误判为基线被改 |
| `test_package_builder.py` | 219 | **Gate C §C.4/§C.5 统一交付构建器（新增，10 项）**：用假引擎客户端把构建器自己的职责钉住——清单保留引擎交付元数据并附逐文件表与整包摘要、包内场景=交付字节（不是引擎的 pretty 副本）、改一个 www/ 文件后磁盘重算的摘要与清单不符（篡改可查）、缺元数据必须 `DELIVERY_INTEGRITY` 而不是静默补默认、同内容重跑幂等、`include_offline=False` 不产出包、路径上留有坏字节时重写而非发出坏字节；**§C.5 三条实测闸门**：浏览器判据不过就没有包也就没有发布、实测结论写在 `offline_verification.json`（含截图哈希与 source=browser:chromium）、客户端不认识实测方法时宁可拒绝也不默认通过 |
| `test_publish_chain.py` | 305 | 发布链（原子性、版本可恢复） |
| `test_contracts_surface.py` | 132 | §6.2 守卫：每个业务接口 2xx 都必须指向具名 DTO（生成物落后于后端即红） |
| `test_teacher_web_e2e.py` | 338 | 切片 8 金路径：真浏览器驱动教师前端走完整使用链（含版本回滚、下载文件本地重算哈希校验）；head 与产物 id 断言改为对照 `jobs.candidate_revision_id` 与 `artifact_id_for(job, "native", sha256)`。**§C.3 起还断言教学视图上屏**：`#teaching-views` 的表头五列与那一行数值（u=30/f=15/v=30/实像/−1），并把屏上的行与磁盘上交付的 `teaching_views.json` 逐值比对；Worker 用 `--planner-static-view measurement_table` 注入视图。版本表行数选择器限定到 `#revision-history`，否则会把记录行也数进去 |
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
| `test_package_builder` | [`application/package_builder.py`](../../python/src/eduforge/application/README.md)（统一交付构建）、`domain/errors.py`（`DeliveryIntegrityError`） |
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
