# migrations — schema 版本推进

**职责**：把「建表」从一次性 DDL 变成**按版本推进、可记账**的过程。上一轮整个 schema 只有 `repositories.JOBS_DDL` 那一串 `create table if not exists`，它对已存在的库**永远不会加列**——`experiment_candidates` 是新表才侥幸能建出来，给老表加列则会静默失败、拖到运行期才炸。本目录负责版本表 `schema_migrations`、迁移清单与 `apply_migrations(conn)`。

## 内容（逐文件）

| 文件 | 职责 |
|---|---|
| `__init__.py` | `MIGRATIONS` 清单（版本 → 名称 → SQL）、`apply_migrations`、`current_version`、`schema_status`。基线迁移 0001 直接引用持久层的 `JOBS_DDL`，**不复制第二份 DDL** |
| `0002_experiment_candidates.sql` | 未发布候选工作态表：`job_id` 主键（一 job 一行）、`state_version`（CAS）、`validation_hash`（内容一变即失效）、`agent_trace`（仅审计） |
| `0003_validation_report_binding.sql` | 给 `validation_reports` 加 `candidate_id`/`content_hash`/`engine_version`/`profile` 四列（Gate C §C.1：报告必须说清验的是哪一版）。全部可空、不改写老行，历史报告按历史现场理解 |

## 与上下层的关系

- 被 [`../README.md`](../README.md) 描述的持久层拥有；调用方是 [`../../../api/main.py`](../../../api/main.py) 的 lifespan 与 [`../../../worker/run.py`](../../../worker/run.py)，两者都只在启动时跑一次。
- 测试夹具也走 `apply_migrations`（见 [`../../../../../../tests/python/test_gate_a_candidate.py`](../../../../../../tests/python/test_gate_a_candidate.py) 的旧库升级用例），不允许测试自建第二套 schema。

## 已知的坑与纪律

- **DDL 的唯一来源仍是 `repositories.JOBS_DDL`**：`tests/python/test_single_publish_path.py::test_ddl_lives_only_in_the_persistence_layer` 会钉住「只有一个文件含 jobs 建表语句」。要加新表就在本目录加一个编号迁移，别把建表语句抄进别处。
- 迁移必须**在新库和旧库都能跑**，所以沿用 `if not exists`；一个迁移跑在一条事务里，失败即整条回滚并留在下一个版本号上。
- 这里没有 `down` 迁移（回滚脚本）。当前阶段靠「备份 + 重建」恢复，真要写回滚先补设计，别顺手写 `drop table`。
- 版本号只增不减：`0001` 是基线，`0002` 是候选表。已应用的版本不会被重复执行，因此**改过已上线的迁移 SQL 不会生效**——要改就加新版本号。
