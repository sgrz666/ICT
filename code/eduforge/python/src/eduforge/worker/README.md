# worker — 任务执行（五阶段 + 租约 + 进程入口）

**职责**：把"一个已落库的任务"推进到终结。三层职责清晰分离：`run.py` 是进程入口（选规划器、连库、循环领取）；`main.py` 是单任务执行器（领任务、落错、崩溃模拟）；`steps.py` 是**生产组合根**（组装全部依赖并实现五阶段）。阶段机本身在 [`../application/coordinator.py`](../application/README.md)。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `errors.py` | 15 | 任务级错误分类：终态错误（写 failed 后不再重试） | `TerminalError` |
| `lease.py` | 151 | **租约守护器（Gate B 起真正接线）**：`from_pool` 从池里单独 acquire 一条连接给心跳用（不与 Agent SQL 抢同一条），后台按 `heartbeat_interval_seconds`（默认 25s）调 `renew_and_check` 续 90s 租约；状态词 `ok/cancelled/stolen/expired/lost/missing/timeout`；`check_active()` 是各阶段与新工具动作前的闸门，`check_now()` 供发布前当场复查；`max_runtime_seconds` 给单任务运行时长封顶 | `LeaseManager`, `from_pool`, `beat`, `check_active`, `check_now` |
| `main.py` | 145 | 单任务执行：`run_once` 领取（attempt 已在 SQL 里 +1）→ 超上限即终态 `MAX_ATTEMPTS_EXCEEDED` → 起心跳守护 → `Coordinator.run`；失败分三类处理：终态写 `failed`、可重试（`RETRYABLE`：OSError/httpx.TransportError/asyncpg.PostgresError）退回 `queued` 并写 `next_run_at` 退避、丢执行权或已取消只记事件不改状态；`SimulatedCrash` 供崩溃恢复测试 | `Worker`, `SimulatedCrash`, `RETRYABLE` |
| `run.py` | 141 | 进程入口 `python -m eduforge.worker.run`：参数解析、启动即 `apply_migrations`、规划器选择（`--planner model\|deep\|static`；`deep` 现在构造的是 **`DeepAgentRunner`**，不再是 `DeepAgentPlanner`；缺 DeepSeek key 拒绝启动——解析见 [`../infrastructure/settings.py`](../infrastructure/README.md) `get_deepseek_api_key()`）、事件循环。`deep` 需要活的库连接，真正构造发生在连库之后 | `main`, `build_parser`, `select_planner`, `STATIC_BANNER` |
| `steps.py` | 400 | **生产组合根**：`Chain` 五阶段实现——planning 交候选 Runner（`DeepAgentRunner`，或由 `ProposalRunner` 适配的旧 `PlannerPort`），editing/building/validating/packaging **全部消费同一行持久候选**；§C.4 起写盘与产物登记统一交 `application.PackageBuilder`（本模块不再自己 `scene_bytes` 落盘），交付完整性失败映射成可见终态 `DELIVERY_INTEGRITY`；`make_worker` 注入 `EngineClient`/`planner`/`lease_token`；`base_untouched` 是真实断言（引擎字段 ∧ 基线修订逐字节复核），纯视图任务不再因此被误判 | `Chain`, `PlannerPort`, `StaticPlanner`, `make_worker`, `artifact_path` |

## 五阶段（`steps.py: Chain`；每个阶段只从 DB/磁盘取事实，保证 at-least-once 可重跑）

| 阶段 | 做什么 | 关键调用 |
|---|---|---|
| planning | 跑执行端口：模型（或固定提案）**通过受控工具直接改动 `experiment_candidates` 那一行**；返回候选完成记录 `AgentRunRecord`（candidate_id、content_hash、state_version、validation_id、terminal_state）。旧 `PlannerPort` 由 `agent/proposal_runner.py` 适配，仍先过 `policy.authorize` 再落候选，`work_order` 照旧写回 jobs 供审计 | `runner.run` → [`../agent/deepagents_runner.py`](../agent/README.md) / [`../agent/proposal_runner.py`](../agent/README.md) |
| editing | 不再重放操作：对**待交付候选**做一次真实引擎观测，并逐字节复核基线修订未被改写 | `EngineClient.apply`, `CandidateService.load` |
| building | 调工具服务那一条 `build_package`：冻结候选、落盘 `revisions/{candidate}/native.json`（+ `teaching_views.json`）、算 sha256、写 `jobs.candidate_revision_id` | `ExperimentToolService.build_package` |
| validating | 对冻结后的候选重跑同一套验证实现（`final=True`：先重新读回候选再冻结再验），报告当场落库并绑定候选内容哈希；payload 里区分 `failed_checks` 与 `unverifiable_checks` | `ExperimentToolService.run_validation` |
| packaging | 校验「报告绑在当前内容哈希上」后交 `PackageBuilder` 建交付字节（含**离线运行包**，§C.4 起 Worker 也建），逐文件回读核对并登记内容派生的 artifacts，再进四道闸门事务；核对不过直接 `DELIVERY_INTEGRITY` | `PackageBuilder`, `CandidateService`, `Publisher.publish` |

> **本轮拆掉的东西**：`Chain._apply()` 在基线上重放 `EditProposal` 的那条路径、以及 `planning`→`operations_from_trace` 的「把模型的成功调用折算成清单」在生产链上的地位。Trace 从此只作审计（`experiment_candidates.agent_trace`）。理由与实况见 [`../../../../../../plan/`](../../../../../../plan/README.md) 里的 `26.10.17_EduForge_GateA_统一候选执行链.md`：那份重放出来的场景从没被模型验过，「验证什么就发布什么」当场失效。

## 与上下层的关系

- 依赖：[`../agent/`](../agent/README.md)、[`../application/`](../application/README.md)、[`../infrastructure/`](../infrastructure/README.md)、[`../validation/`](../validation/README.md)、[`../domain/`](../domain/README.md)。
- 被谁用：部署脚本 `scripts/eduforge.ps1` 的 `up` 起本进程；测试直接起真实进程（`python -m eduforge.worker.run --once`，见 [`../../../../tests/python/test_chain_worker.py`](../../../../tests/python/test_chain_worker.py)、[`test_teacher_web_e2e.py`](../../../../tests/python/test_teacher_web_e2e.py)）。
- 阶段机：[`../application/coordinator.py`](../application/README.md)（按 `stage_done` 事件断点恢复）。

## 已知的坑与纪律

- **租约心跳已接线（2026-10-17 Gate B）**：`lease.py` 的 `LeaseManager` 过去调的是 `JobRepository` 上并不存在的 `heartbeat`（会 `AttributeError`），所以「有心跳」只是文档说法，真实行为是长任务自己把执行权睡丢。现在它走 `renew_and_check`，并且**必须从连接池单独拿一条连接**——asyncpg 单连接不允许并发查询，心跳与 Agent SQL 共用一条会互相打断。给 `make_worker` 传 `pool=` 才有心跳，生产入口 `worker/run.py` 已改为建池并传入；不传池只该出现在单元测试里。实测证据：[`test_gate_b_execution_rights.py`](../../../../tests/python/test_gate_b_execution_rights.py) 的第一条用例带**控制组**（有心跳时别人领不走、没心跳时同一个慢任务在租约到期后被抢走）。
- `attempt` 与 `next_run_at` 现在真的被写：`CLAIM_SQL` 领取即 `attempt + 1`，可重试失败经 `retry_later` 退回 `queued` 并把 `next_run_at` 推到未来（`backoff_seconds=(5,15,60)` 有限退避），超过 `max_attempts`（默认 5）由 `run_once` 终态化为 `MAX_ATTEMPTS_EXCEEDED`。**取消现在会中断执行中的阶段**：每个阶段与每次工具写动作前都查 `status`，`cancelled` 直接停（`JOB_CANCELLED`），不再只靠发布事务间接生效。
- **执行权 token 的来源是纪律**：Runner 从前必须回读 `jobs.lease_token` 来构造 `JobContext`，于是被抢权的旧 Worker 会把**新主人的 token 当成自己的**继续写（本轮实测抓到，`test_two_workers_cannot_double_publish` 钉住）。现在 token 由 Worker 领取时那一个注入（`Chain` 把 `guard` 与 `lease_token` 一起交给端口），旧 Worker 在第一次写动作前就被 `LEASE_LOST` 拦下。
- `StaticPlanner`（`--planner-static-focal`）只用于**链路验证**；其产物不构成"Agent 规划"证据，README 与报告里不得含糊表述。`scripts/eduforge.ps1` 已不再无 key 时自动注入它——现在必须显式 `EDUFORGE_ALLOW_STATIC_PLANNER=1`，否则 Worker 拒绝启动并说明原因。本轮它经 `agent/proposal_runner.py` 接到候选链上，**不再有一套自己的重放实现**。
- **候选版本 id 由内容哈希派生**（`revision_id_for(job_id, content_hash)`、`artifact_id_for(job_id, name, digest)`，规则住在持久层）。同一份内容重跑落在同一个 id 上（幂等），内容变了才是新版本——这让「先改 A 再改 B」不会退化成「两个 id 相同、发布 A」。测试不再自己拼 id，改读 `jobs.candidate_revision_id`。
- `Publisher.publish` / `JobRepository.publish` 带 `close_job` 参数：默认 True 保持旧语义（发布即收 job 为 succeeded）；连续编辑场景由后端传 False，才能在一个 job 内提交多个版本（工具层发布后还会 `rebase` 候选基线，否则第二次发布仍拿最初的 base 撞乐观并发）。
- 无 key 拒绝启动是刻意设计：宁可不跑（明确失败），不允许桩模型冒充真实规划。
