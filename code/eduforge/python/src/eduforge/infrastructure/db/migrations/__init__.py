"""版本化 schema 迁移：把「建表」从一次性 DDL 变成可追踪、可增列的过程。

为什么不能继续只靠 `create table if not exists`：那张语句只能新增表，
**给已有表加列永远不会生效**。旧库上跑新代码时，缺列会以运行期错误的方式暴露，
而不是在启动时明确失败——`experiment_candidates` 正是这种情况。

规则：
- `schema_migrations` 记录已应用的版本号；每个迁移在自己的事务里执行；
- 迁移必须在新库和旧库都能跑，所以基线迁移沿用持久层那份 `JOBS_DDL`
  （全部 `if not exists`），旧库重放无害；
- DDL 的唯一来源仍是 `repositories.py`（`test_ddl_lives_only_in_the_persistence_layer`
  钉着这一点），这里只负责「按版本顺序应用并记账」。
"""
from __future__ import annotations

from pathlib import Path

import asyncpg

SCHEMA_VERSION_TABLE = "schema_migrations"

BASELINE_VERSION = 1
BASELINE_NAME = "baseline_jobs_schema"
CANDIDATES_VERSION = 2
CANDIDATES_NAME = "experiment_candidates"

_MIGRATION_DIR = Path(__file__).resolve().parent


def _candidates_sql() -> str:
    # 迁移 SQL 与代码同目录存放：评审时能一眼看到落库的到底是哪几列
    return (_MIGRATION_DIR / "0002_experiment_candidates.sql").read_text(encoding="utf-8")


async def current_version(conn: asyncpg.Connection) -> int:
    await conn.execute(
        f"""create table if not exists {SCHEMA_VERSION_TABLE} (
              version int primary key,
              name text not null,
              applied_at timestamptz not null default now()
            )"""
    )
    return await conn.fetchval(
        f"select coalesce(max(version), 0) from {SCHEMA_VERSION_TABLE}"
    ) or 0


async def apply_migrations(conn: asyncpg.Connection) -> list[int]:
    """把库推到最新版本，返回本次实际应用的版本号列表（已应用的不重复执行）。"""
    from eduforge.infrastructure.db.repositories import JOBS_DDL

    migrations: list[tuple[int, str, str]] = [
        (BASELINE_VERSION, BASELINE_NAME, JOBS_DDL),
        (CANDIDATES_VERSION, CANDIDATES_NAME, _candidates_sql()),
    ]
    head = await current_version(conn)
    applied: list[int] = []
    for version, name, sql in migrations:
        if version <= head:
            continue
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                f"insert into {SCHEMA_VERSION_TABLE} (version, name) values ($1, $2)",
                version, name,
            )
        applied.append(version)
    return applied


async def schema_status(conn: asyncpg.Connection) -> dict[str, object]:
    return {
        "version": await current_version(conn),
        "tables": [
            r["tablename"]
            for r in await conn.fetch(
                "select tablename from pg_tables where schemaname = 'public' order by tablename"
            )
        ],
    }
