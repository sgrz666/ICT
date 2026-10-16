# worker — 任务执行（五阶段 + 租约 + 进程入口）

**职责**：把"一个已落库的任务"推进到终结。三层职责清晰分离：`run.py` 是进程入口（选规划器、连库、循环领取）；`main.py` 是单任务执行器（领任务、落错、崩溃模拟）；`steps.py` 是**生产组合根**（组装全部依赖并实现五阶段）。阶段机本身在 [`../application/coordinator.py`](../application/README.md)。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `errors.py` | 15 | 任务级错误分类：终态错误（写 failed 后不再重试） | `TerminalError` |
| `lease.py` | 78 | 租约守护器（心跳续租、过期抛错）。**未接线**——运行时靠 `repo.claim` 的 `lease_token` 传递，而非此守护器 | `LeaseManager` |
| `main.py` | 73 | 单任务执行：`run_once` 领取 → 设 steps → `Coordinator.run`；捕获 `TerminalError`/`Rejected` 落 failed；`SimulatedCrash` 供崩溃恢复测试 | `Worker`, `SimulatedCrash` |
| `run.py` | 133 | 进程入口 `python -m eduforge.worker.run`：参数解析、规划器选择（`--planner model\|deep\|static`；缺 DeepSeek key 拒绝启动——解析见 [`../infrastructure/settings.py`](../infrastructure/README.md) `get_deepseek_api_key()`）、事件循环。`deep` 需要活的库连接，真正构造发生在连库之后 | `main`, `build_parser`, `select_planner`, `STATIC_BANNER` |
| `steps.py` | 372 | **生产组合根**：`Chain` 五阶段实现；`make_worker` 注入 `EngineClient`/`planner`/`lease_token`；`base_untouched` 改为**真实断言**（引擎字段 ∧ 基线修订逐字节复核） | `Chain`, `PlannerPort`, `StaticPlanner`, `make_worker` |

## 五阶段（`steps.py: Chain`；每个阶段只从 DB/磁盘取事实，保证 at-least-once 可重跑）

| 阶段 | 做什么 | 关键调用 |
|---|---|---|
| planning | 规划 + 服务端二次授权，`work_order` 写回 jobs；`route=='code'` 直接判 `CODE_ROUTE_NOT_EXECUTED` | `planner.plan` → [`../agent/policy.py`](../agent/README.md) `authorize` |
| editing | 交 Engine Host 改上游场景并真实仿真 | `EngineClient.apply` |
| building | 序列化候选场景落盘（`revisions/{candidate}/native.json`）+ sha256 + 派生 `candidate_revision_id` | `scene_bytes`, `derived_id` |
| validating | 门禁检查构建报告并落库 | `build_report`, `Publisher.record_report` |
| packaging | 仅 `verdict=passed` 才发布（单事务） | `Publisher.publish` |

## 与上下层的关系

- 依赖：[`../agent/`](../agent/README.md)、[`../application/`](../application/README.md)、[`../infrastructure/`](../infrastructure/README.md)、[`../validation/`](../validation/README.md)、[`../domain/`](../domain/README.md)。
- 被谁用：部署脚本 `scripts/eduforge.ps1` 的 `up` 起本进程；测试直接起真实进程（`python -m eduforge.worker.run --once`，见 [`../../../../tests/python/test_chain_worker.py`](../../../../tests/python/test_chain_worker.py)、[`test_teacher_web_e2e.py`](../../../../tests/python/test_teacher_web_e2e.py)）。
- 阶段机：[`../application/coordinator.py`](../application/README.md)（按 `stage_done` 事件断点恢复）。

## 已知的坑与纪律

- **租约从不续期（本轮仍未修，是 `--planner deep` 走 Worker 的首要风险）**：`JobRepository.renew_lease`（[`../infrastructure/db/repositories.py`](../infrastructure/db/repositories.py)）零调用者，`lease.py` 的 `LeaseManager` 也没接线——它调的是 `heartbeat`，而 `JobRepository` 上根本没有这个方法（只有 `renew_lease`），照现状接上去会 `AttributeError`。默认租约 90s，而真模型多轮循环几乎必然超过 90s：任务会丢执行权、在 packaging 撞 `LeaseLost`。本轮的 Deep Agents 实测是**直接驱动工具服务**（夹具里显式插一条 300–600s 租约的 job），所以这条路能过；**「Deep Agents 经 Worker 端到端跑通」尚未实测，属 pending**。
- 同理，`attempt` 与 `next_run_at` 只在 DDL 里存在、运行时代码从不移写，所以**没有任何重试记账与退避**；取消也不会中断执行中的阶段，它只在发布时通过「job 必须仍是 running」间接生效。
- `StaticPlanner`（`--planner-static-focal`）只用于**链路验证**；其产物不构成"Agent 规划"证据，README 与报告里不得含糊表述。`scripts/eduforge.ps1` 已不再无 key 时自动注入它——现在必须显式 `EDUFORGE_ALLOW_STATIC_PLANNER=1`，否则 Worker 拒绝启动并说明原因。
- `derived_id` 本轮移到持久层（`infrastructure/db/repositories.py`），Worker 与 [`../experiment_tools/`](../experiment_tools/README.md) 共用同一条派生规则；新增写盘产物必须经它派生 id，否则重跑产生孤儿文件。
- `Publisher.publish` / `JobRepository.publish` 新增 `close_job` 参数：默认 True 保持旧语义（发布即收 job 为 succeeded）；连续编辑场景由后端传 False，才能在一个 job 内提交多个版本。
- 无 key 拒绝启动是刻意设计：宁可不跑（明确失败），不允许桩模型冒充真实规划。
