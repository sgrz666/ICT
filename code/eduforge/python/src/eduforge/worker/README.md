# worker — 任务执行（五阶段 + 租约 + 进程入口）

**职责**：把"一个已落库的任务"推进到终结。三层职责清晰分离：`run.py` 是进程入口（选规划器、连库、循环领取）；`main.py` 是单任务执行器（领任务、落错、崩溃模拟）；`steps.py` 是**生产组合根**（组装全部依赖并实现五阶段）。阶段机本身在 [`../application/coordinator.py`](../application/README.md)。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `errors.py` | 15 | 任务级错误分类：终态错误（写 failed 后不再重试） | `TerminalError` |
| `lease.py` | 78 | 租约守护器（心跳续租、过期抛错）。**未接线**——运行时靠 `repo.claim` 的 `lease_token` 传递，而非此守护器 | `LeaseManager` |
| `main.py` | 73 | 单任务执行：`run_once` 领取 → 设 steps → `Coordinator.run`；捕获 `TerminalError`/`Rejected` 落 failed；`SimulatedCrash` 供崩溃恢复测试 | `Worker`, `SimulatedCrash` |
| `run.py` | 113 | 进程入口 `python -m eduforge.worker.run`：参数解析、规划器选择（缺 DeepSeek key 拒绝启动——解析见 [`../infrastructure/settings.py`](../infrastructure/README.md) `get_deepseek_api_key()`；除非 `--planner-static-focal`）、事件循环 | `main`, `build_parser`, `select_planner`, `STATIC_BANNER` |
| `steps.py` | 359 | **生产组合根**：`Chain` 五阶段实现；`make_worker` 注入 `EngineClient`/`planner`/`lease_token`；`derived_id(job_id, kind)` 保证重跑幂等 | `Chain`, `PlannerPort`, `StaticPlanner`, `make_worker`, `derived_id` |

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

- `lease.py` 的 `LeaseManager` **未接线**：真正的租约语义在 [`../infrastructure/db/repositories.py`](../infrastructure/README.md) 的 `claim`/`heartbeat` SQL 里——不要用本文件推断租约行为。
- `StaticPlanner`（`--planner-static-focal`）只用于**链路验证**；其产物不构成"Agent 规划"证据，README 与报告里不得含糊表述。
- `derived_id` 是幂等的根基：新增写盘产物必须经它派生 id，否则重跑产生孤儿文件。
- 无 key 拒绝启动是刻意设计：宁可不跑（明确失败），不允许桩模型冒充真实规划。
