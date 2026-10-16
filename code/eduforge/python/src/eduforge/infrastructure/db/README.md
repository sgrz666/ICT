# db — Postgres 持久层

**职责**：全部数据库访问都在本目录，裸 SQL + asyncpg（不走 ORM）。核心职责包括：任务领取的锁语义（`FOR UPDATE SKIP LOCKED` 租约）、事件时间线、未发布候选工作态（`experiment_candidates`，含 CAS 与验证失效）、版本与产物的**单事务发布**。整个系统的并发正确性由这里的 SQL 保证。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `repositories.py` | 344 | **持久层核心**：`JOBS_DDL` 建表、`CLAIM_SQL` 领取语义、`derived_id(job_id, kind)` + `ID_NAMESPACE`、`JobRepository`（create_job 幂等 / claim / renew_lease / mark_failed / append_event / publish 发布事务，`publish` 带 `close_job`）。本轮新增三条**内容派生**的 id 规则：`candidate_id_for(job)`（一 job 一候选）、`revision_id_for(job, content_hash)`、`artifact_id_for(job, name, digest)` | `JOBS_DDL`, `CLAIM_SQL`, `request_hash`, `derived_id`, `candidate_id_for`, `revision_id_for`, `artifact_id_for`, `DuplicateIdempotencyKey`, `LeaseLost`, `RevisionConflict`, `JobRepository` |
| `candidate_repository.py` | 206 | 未发布候选工作态的仓储：`initialize`（幂等，按 job 唯一）、`load`、`write`（`state_version` CAS，写成功即清空验证绑定）、`bind_validation`（只绑当前 `content_hash`）、`freeze`、`rebase`（发布后推进基线，支持连续编辑）、`attach_trace`（仅审计）。异常：`CandidateNotFound` / `CandidateVersionConflict` / `CandidateScopeConflict` | `CandidateRepository`, `CANDIDATE_COLUMNS` |
| [`migrations/`](migrations/README.md) | 80 + 1 SQL | schema 版本推进：`schema_migrations` 记账、`apply_migrations(conn)` 按版本执行。0001 引用持久层那份 `JOBS_DDL`（不复制第二份 DDL），0002 建 `experiment_candidates` | `apply_migrations`, `current_version`, `schema_status` |
| `models.py` | 18 | 表清单与 DDL 重导出；**仅测试引用** | `JOBS_DDL`（重导）, `TABLES` |
| `session.py` | 33 | 连接池管理器 `DatabaseSessionManager`；**未被 src 使用**（api/main 自建 pool、worker/run 直接 `asyncpg.connect`） | `DatabaseSessionManager` |

## 被依赖关系（谁用 `repositories.py`）

- [`../../api/main.py`](../../api/main.py)（启动跑 `apply_migrations`，路由落库与查询）、[`../../worker/run.py`](../../worker/run.py)（启动跑 `apply_migrations`）、[`../../worker/main.py`](../../worker/main.py)（claim）、[`../../worker/steps.py`](../../worker/steps.py)（阶段内读写与 publish）、[`../../application/`](../../application/README.md) 全部服务类（`candidate_service` 用本层 `CandidateRepository`）。
- 测试覆盖最广：leases / cancel / recovery / rollback / publish 五个 gate5-6 文件都直接打它；建库统一走 `apply_migrations`（不再各跑一份 `JOBS_DDL`）。

## 与上下层的关系

- 上层：[`../../domain/contracts.py`](../../domain/contracts.py) 定义出入参模型；[`../../domain/models.py`](../../domain/README.md) 的 dataclass **未被本层使用**（历史定义）。
- DDL 唯一来源：`JOBS_DDL` 仍是**建表语句的唯一出处**，[`migrations/`](migrations/README.md) 只负责按版本推进并记账（`schema_migrations`）。建库入口统一为 `apply_migrations(conn)`——`api/main.py` 的 lifespan、`worker/run.py` 的 loop、测试夹具三处都调它，不再各跑一份 DDL。

## 已知的坑与纪律

- **事务与锁在 SQL 里，不在 Python 里**：publish 是单事务写四件事（候选版本、产物、head 前移、任务状态），"四道闸门"（verdict=passed、有效租约、未取消、基础版本一致）都在 SQL 条件中——改发布语义先读 `publish` 的 SQL。`close_job=False` 时只跳过第四件（任务状态），前三件照做，用于一个 job 内连续提交多个版本。
- **迁移已版本化，但仍没有 `down`**：本轮补上了 `schema_migrations` + 顺序应用（旧库能拿到新表新列，`test_gate_a_candidate.py::test_migration_runs_on_old_database_and_is_idempotent` 钉住了这一点）。回滚脚本仍不存在，恢复靠备份重建；已上线的迁移 SQL 改了也不会重放，要加新版本号。
- **候选的 CAS 在 SQL 里**：`write` 的 `where job_id = $1 and state_version = $5` 是「两个进程同一版候选先后写、后者必须失败」的唯一实现处。调用方**必须把自己读到的那个 `state_version` 传进来**——若先读最新再更新，守卫就成了装饰（本轮就修过一次这种写法）。
- 候选行的 `validation_hash` 只与当前 `content_hash` 相等时才算「验过」：内容一变，`write` 当场清空验证绑定。别指望上层「记得清报告」。
- `agent_trace` 是**审计列**，不参与任何业务判定；把它当状态源读就是回到 `operations_from_trace` 的老路（Gate A 已经拆掉那条路径，见 [`../../worker/README.md`](../../worker/README.md)）。
- `claim` 的 `FOR UPDATE SKIP LOCKED` 是 at-least-once 的基础：任务可重跑，阶段实现必须幂等（配合本层的 `derived_id` 与内容派生 id）。
- `JobRepository` **没有** `heartbeat` 方法（端口 `domain/ports.py` 里声明了这个名字，`worker/lease.py` 还在调它）——真实存在的是 `renew_lease`，且它当前零调用者。别把端口当实现读。
- `session.py` 与 `models.py` 是"定义先行"的预留件——不要误以为连接管理经 `session.py`。
