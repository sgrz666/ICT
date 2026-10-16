# db — Postgres 持久层

**职责**：全部数据库访问都在本目录，裸 SQL + asyncpg（不走 ORM）。核心职责包括：任务领取的锁语义（`FOR UPDATE SKIP LOCKED` 租约）、事件时间线、版本与产物的**单事务发布**。整个系统的并发正确性由这里的 SQL 保证。

## 内容（逐文件）

| 文件 | 行数 | 职责 | 关键符号 |
|---|---|---|---|
| `repositories.py` | 310 | **持久层核心**：`JOBS_DDL` 建表、`CLAIM_SQL` 领取语义、`JobRepository`（create_job 幂等 / claim / heartbeat / mark_failed / append_event / publish 发布事务） | `JOBS_DDL`, `CLAIM_SQL`, `request_hash`, `DuplicateIdempotencyKey`, `LeaseLost`, `RevisionConflict`, `JobRepository` |
| `models.py` | 18 | 表清单与 DDL 重导出；**仅测试引用** | `JOBS_DDL`（重导）, `TABLES` |
| `session.py` | 33 | 连接池管理器 `DatabaseSessionManager`；**未被 src 使用**（api/main 自建 pool、worker/run 直接 `asyncpg.connect`） | `DatabaseSessionManager` |

## 被依赖关系（谁用 `repositories.py`）

- [`../../api/main.py`](../../api/main.py)（路由落库与查询）、[`../../worker/main.py`](../../worker/main.py)（claim）、[`../../worker/steps.py`](../../worker/steps.py)（阶段内读写与 publish）、[`../../application/`](../../application/README.md) 全部服务类。
- 测试覆盖最广：leases / cancel / recovery / rollback / publish 五个 gate5-6 文件都直接打它。

## 与上下层的关系

- 上层：[`../../domain/contracts.py`](../../domain/contracts.py) 定义出入参模型；[`../../domain/models.py`](../../domain/README.md) 的 dataclass **未被本层使用**（历史定义）。
- DDL 唯一来源：`JOBS_DDL` 在建库与测试夹具间共享；改表结构要同时看 `api/main.py` 与 `tests/python/conftest.py` 的建库路径。

## 已知的坑与纪律

- **事务与锁在 SQL 里，不在 Python 里**：publish 是单事务写四件事（候选版本、产物、head 前移、任务状态），"四道闸门"（verdict=passed、有效租约、未取消、基础版本一致）都在 SQL 条件中——改发布语义先读 `publish` 的 SQL。
- `claim` 的 `FOR UPDATE SKIP LOCKED` 是 at-least-once 的基础：任务可重跑，阶段实现必须幂等（配合 [`../../worker/steps.py`](../../worker/steps.py) 的 `derived_id`）。
- `session.py` 与 `models.py` 是"定义先行"的预留件——不要误以为连接管理经 `session.py`。
