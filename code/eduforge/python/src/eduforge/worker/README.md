# worker — 任务执行（五阶段 + 租约 + 进程入口）

**职责**：把"一个已落库的任务"推进到终结。三层职责清晰分离：`run.py` 是进程入口（选规划器、连库、循环领取）；`main.py` 是单任务执行器（领任务、落错、崩溃模拟）；`steps.py` 是**生产组合根**（组装全部依赖并实现五阶段）。阶段机本身在 [`../application/coordinator.py`](../application/README.md)。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `errors.py` | 15 | 任务级错误分类：终态错误（写 failed 后不再重试） | `TerminalError` |
| `lease.py` | 78 | 租约守护器（心跳续租、过期抛错）。**未接线**——运行时靠 `repo.claim` 的 `lease_token` 传递，而非此守护器 | `LeaseManager` |
| `main.py` | 73 | 单任务执行：`run_once` 领取 → 设 steps → `Coordinator.run`；捕获 `TerminalError`/`Rejected` 落 failed；`SimulatedCrash` 供崩溃恢复测试 | `Worker`, `SimulatedCrash` |
| `run.py` | 135 | 进程入口 `python -m eduforge.worker.run`：参数解析、启动即 `apply_migrations`、规划器选择（`--planner model\|deep\|static`；`deep` 现在构造的是 **`DeepAgentRunner`**，不再是 `DeepAgentPlanner`；缺 DeepSeek key 拒绝启动——解析见 [`../infrastructure/settings.py`](../infrastructure/README.md) `get_deepseek_api_key()`）、事件循环。`deep` 需要活的库连接，真正构造发生在连库之后 | `main`, `build_parser`, `select_planner`, `STATIC_BANNER` |
| `steps.py` | 385 | **生产组合根**：`Chain` 五阶段实现——planning 交候选 Runner（`DeepAgentRunner`，或由 `ProposalRunner` 适配的旧 `PlannerPort`），editing/building/validating/packaging **全部消费同一行持久候选**；`make_worker` 注入 `EngineClient`/`planner`/`lease_token`；`base_untouched` 是真实断言（引擎字段 ∧ 基线修订逐字节复核），纯视图任务不再因此被误判 | `Chain`, `PlannerPort`, `StaticPlanner`, `make_worker`, `scene_bytes`, `artifact_path` |

## 五阶段（`steps.py: Chain`；每个阶段只从 DB/磁盘取事实，保证 at-least-once 可重跑）

| 阶段 | 做什么 | 关键调用 |
|---|---|---|
| planning | 跑执行端口：模型（或固定提案）**通过受控工具直接改动 `experiment_candidates` 那一行**；返回候选完成记录 `AgentRunRecord`（candidate_id、content_hash、state_version、validation_id、terminal_state）。旧 `PlannerPort` 由 `agent/proposal_runner.py` 适配，仍先过 `policy.authorize` 再落候选，`work_order` 照旧写回 jobs 供审计 | `runner.run` → [`../agent/deepagents_runner.py`](../agent/README.md) / [`../agent/proposal_runner.py`](../agent/README.md) |
| editing | 不再重放操作：对**待交付候选**做一次真实引擎观测，并逐字节复核基线修订未被改写 | `EngineClient.apply`, `CandidateService.load` |
| building | 调工具服务那一条 `build_package`：冻结候选、落盘 `revisions/{candidate}/native.json`（+ `teaching_views.json`）、算 sha256、写 `jobs.candidate_revision_id` | `ExperimentToolService.build_package` |
| validating | 对冻结后的候选重跑同一套验证实现，报告当场落库并绑定候选内容哈希 | `ExperimentToolService.run_validation` |
| packaging | 校验「报告绑在当前内容哈希上」+ 交付字节与候选逐字节一致，再进四道闸门事务；不一致直接 `ARTIFACT_CONTENT_MISMATCH` | `CandidateService`, `Publisher.publish` |

> **本轮拆掉的东西**：`Chain._apply()` 在基线上重放 `EditProposal` 的那条路径、以及 `planning`→`operations_from_trace` 的「把模型的成功调用折算成清单」在生产链上的地位。Trace 从此只作审计（`experiment_candidates.agent_trace`）。理由与实况见 [`../../../../../../plan/`](../../../../../../plan/README.md) 里的 `26.10.17_EduForge_GateA_统一候选执行链.md`：那份重放出来的场景从没被模型验过，「验证什么就发布什么」当场失效。

## 与上下层的关系

- 依赖：[`../agent/`](../agent/README.md)、[`../application/`](../application/README.md)、[`../infrastructure/`](../infrastructure/README.md)、[`../validation/`](../validation/README.md)、[`../domain/`](../domain/README.md)。
- 被谁用：部署脚本 `scripts/eduforge.ps1` 的 `up` 起本进程；测试直接起真实进程（`python -m eduforge.worker.run --once`，见 [`../../../../tests/python/test_chain_worker.py`](../../../../tests/python/test_chain_worker.py)、[`test_teacher_web_e2e.py`](../../../../tests/python/test_teacher_web_e2e.py)）。
- 阶段机：[`../application/coordinator.py`](../application/README.md)（按 `stage_done` 事件断点恢复）。

## 已知的坑与纪律

- **租约从不续期（本轮仍未修，是 `--planner deep` 走 Worker 的首要风险）**：`JobRepository.renew_lease`（[`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)）零调用者，`lease.py` 的 `LeaseManager` 也没接线——它调的是 `heartbeat`，而 `JobRepository` 上根本没有这个方法（只有 `renew_lease`），照现状接上去会 `AttributeError`。默认租约 90s，而真模型多轮循环几乎必然超过 90s：任务会丢执行权、在 packaging 撞 `LeaseLost`。本轮已实测的是**脚本化模型经 `make_worker` 跑完五阶段并交付**（[`test_gate_a_candidate.py`](../../../../tests/python/test_gate_a_candidate.py) 末条用例，夹具里给 job 显式设 600s 租约）；**真模型经 Worker 全链端到端仍是 pending**（缺 key，且必须先补心跳）。
- 同理，`attempt` 与 `next_run_at` 只在 DDL 里存在、运行时代码从不移写，所以**没有任何重试记账与退避**；取消也不会中断执行中的阶段，它只在发布时通过「job 必须仍是 running」间接生效。
- `StaticPlanner`（`--planner-static-focal`）只用于**链路验证**；其产物不构成"Agent 规划"证据，README 与报告里不得含糊表述。`scripts/eduforge.ps1` 已不再无 key 时自动注入它——现在必须显式 `EDUFORGE_ALLOW_STATIC_PLANNER=1`，否则 Worker 拒绝启动并说明原因。本轮它经 `agent/proposal_runner.py` 接到候选链上，**不再有一套自己的重放实现**。
- **候选版本 id 由内容哈希派生**（`revision_id_for(job_id, content_hash)`、`artifact_id_for(job_id, name, digest)`，规则住在持久层）。同一份内容重跑落在同一个 id 上（幂等），内容变了才是新版本——这让「先改 A 再改 B」不会退化成「两个 id 相同、发布 A」。测试不再自己拼 id，改读 `jobs.candidate_revision_id`。
- `Publisher.publish` / `JobRepository.publish` 带 `close_job` 参数：默认 True 保持旧语义（发布即收 job 为 succeeded）；连续编辑场景由后端传 False，才能在一个 job 内提交多个版本（工具层发布后还会 `rebase` 候选基线，否则第二次发布仍拿最初的 base 撞乐观并发）。
- 无 key 拒绝启动是刻意设计：宁可不跑（明确失败），不允许桩模型冒充真实规划。
