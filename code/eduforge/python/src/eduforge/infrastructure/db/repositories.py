"""任务与版本的持久层。

只用 asyncpg 裸 SQL：计划 §4.8 的领取语义依赖 PostgreSQL 的
`FOR UPDATE SKIP LOCKED`，这正是要验的东西，套 ORM 反而遮住它。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

import asyncpg

JOBS_DDL = """
create table if not exists jobs (
  id uuid primary key,
  owner_id text not null,
  experiment_id uuid not null,
  base_revision uuid not null,
  prompt text,
  status text not null,
  stage text,
  attempt int not null default 0,
  idempotency_key uuid not null,
  request_hash text not null,
  lease_token text,
  lease_until timestamptz,
  next_run_at timestamptz not null default now(),
  candidate_revision_id uuid,
  work_order jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists jobs_idempotency_uq
  on jobs (owner_id, idempotency_key);

create table if not exists experiments (
  id uuid primary key,
  owner_id text not null,
  template_id text not null,
  head_revision_id uuid
);

create table if not exists experiment_revisions (
  id uuid primary key,
  experiment_id uuid not null references experiments(id),
  parent_id uuid,
  engine_id text not null,
  native_data jsonb not null,
  lesson jsonb,
  bindings jsonb,
  created_at timestamptz not null default now()
);

create table if not exists artifacts (
  id uuid primary key,
  revision_id uuid not null references experiment_revisions(id),
  storage_key text not null,
  sha256 text not null,
  media_type text not null,
  created_at timestamptz not null default now()
);

create table if not exists validation_reports (
  id uuid primary key,
  job_id uuid not null references jobs(id),
  checks jsonb not null,
  verdict text not null,
  created_at timestamptz not null default now()
);

create table if not exists job_events (
  job_id uuid not null references jobs(id),
  sequence int not null,
  stage text,
  event_type text not null,
  payload jsonb,
  created_at timestamptz not null default now(),
  primary key (job_id, sequence)
);
"""

CLAIM_SQL = """
WITH candidate AS (
    SELECT id
    FROM jobs
    WHERE
        status IN ('queued', 'running')
        AND next_run_at <= now()
        AND (
            lease_until IS NULL
            OR lease_until < now()
        )
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE jobs AS job
SET
    status = 'running',
    lease_token = $1,
    lease_until = now() + make_interval(secs => $2),
    updated_at = now()
FROM candidate
WHERE job.id = candidate.id
RETURNING job.*;
"""


def request_hash(experiment_id: UUID, base_revision: UUID, prompt: str) -> str:
    payload = json.dumps(
        {"experiment_id": str(experiment_id), "base_revision": str(base_revision), "prompt": prompt},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DuplicateIdempotencyKey(Exception):
    """同一个幂等键配了不同请求内容。"""


class LeaseLost(Exception):
    """执行权已不在自己手上，禁止继续推进或发布。"""


class RevisionConflict(Exception):
    """教师在任务执行期间产生了其他版本。"""


class JobRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def create_job(
        self,
        *,
        job_id: UUID,
        owner_id: str,
        experiment_id: UUID,
        base_revision: UUID,
        prompt: str,
        idempotency_key: UUID,
    ) -> asyncpg.Record:
        h = request_hash(experiment_id, base_revision, prompt)
        existing = await self.conn.fetchrow(
            "select request_hash from jobs where owner_id = $1 and idempotency_key = $2",
            owner_id,
            idempotency_key,
        )
        if existing is not None:
            # 同键同内容 = 幂等重放，返回既有任务；同键不同内容 = 冲突
            if existing["request_hash"] == h:
                return await self.conn.fetchrow("select * from jobs where idempotency_key = $1", idempotency_key)
            raise DuplicateIdempotencyKey(str(idempotency_key))

        return await self.conn.fetchrow(
            """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                                 idempotency_key, request_hash)
               values ($1,$2,$3,$4,$7,'queued',$5,$6) returning *""",
            job_id, owner_id, experiment_id, base_revision, idempotency_key, h, prompt,
        )

    async def cancel(self, job_id: UUID, owner_id: str) -> str:
        """标记取消。已成功的任务不回滚——取消只对未完成的生效。

        返回最终状态，调用方据此决定是 202 还是 409。
        """
        row = await self.conn.fetchrow(
            """update jobs
               set status = case when status = 'succeeded' then status else 'cancelled' end,
                   updated_at = now()
               where id = $1 and owner_id = $2
               returning status""",
            job_id, owner_id,
        )
        if row is None:
            raise KeyError(str(job_id))
        return row["status"]

    async def mark_failed(self, job_id: UUID, lease_token: str, error_code: str) -> str | None:
        """终态失败。守卫与发布同构：只有持有效租约的 worker 能写，
        已成功的任务不被改写成失败（那等于把发布出去的版本抹掉）。"""
        row = await self.conn.fetchrow(
            """update jobs
               set status = case when status = 'succeeded' then status else 'failed' end,
                   error_code = case when status = 'succeeded' then error_code else $3 end,
                   updated_at = now()
               where id = $1 and lease_token = $2 and status = 'running' and lease_until > now()
               returning status""",
            job_id, lease_token, error_code,
        )
        return row["status"] if row else None

    async def claim(self, lease_token: str, lease_seconds: int = 90) -> asyncpg.Record | None:
        return await self.conn.fetchrow(CLAIM_SQL, lease_token, float(lease_seconds))

    async def renew_lease(self, job_id: UUID, lease_token: str, lease_seconds: int = 90) -> bool:
        r = await self.conn.execute(
            """update jobs set lease_until = now() + make_interval(secs => $3), updated_at = now()
               where id = $1 and lease_token = $2""",
            job_id,
            lease_token,
            float(lease_seconds),
        )
        return r.endswith("1")

    async def set_stage(self, job_id: UUID, lease_token: str, stage: str) -> bool:
        r = await self.conn.execute(
            """update jobs set stage = $3, updated_at = now()
               where id = $1 and lease_token = $2""",
            job_id,
            lease_token,
            stage,
        )
        return r.endswith("1")

    async def append_event(
        self, job_id: UUID, *, stage: str | None, event_type: str, payload: dict | None = None
    ) -> int:
        """进度事件按 (job_id, sequence) 递增追加。恢复执行靠它判断走到哪一步。"""
        seq = await self.conn.fetchval(
            "select coalesce(max(sequence), 0) + 1 from job_events where job_id = $1", job_id
        )
        await self.conn.execute(
            """insert into job_events (job_id, sequence, stage, event_type, payload)
               values ($1,$2,$3,$4,$5::jsonb)""",
            job_id, seq, stage, event_type, json.dumps(payload or {}),
        )
        return seq

    async def events(self, job_id: UUID):
        return await self.conn.fetch(
            "select sequence, stage, event_type, payload from job_events where job_id = $1 order by sequence",
            job_id,
        )

    async def publish(
        self,
        *,
        job_id: UUID,
        lease_token: str,
        experiment_id: UUID,
        base_revision: UUID,
        candidate_revision_id: UUID,
        native_data: dict,
        checks_passed: bool,
        artifacts: list[dict] | None = None,
        cancelled: bool = False,
        lesson: dict | None = None,
        bindings: dict | None = None,
    ) -> None:
        """§3.5 的发布事务：执行权、取消、验证、基础版本四道闸门后写版本。

        必须在同一个事务里插入版本、文件索引并推进 head——分开写会出现
        head 指向不存在版本的中闲状态。artifacts 外键指向本事务插入的
        experiment_revisions 行，所以文件索引只能在发布时登记。
        """
        if cancelled:
            raise LeaseLost("cancelled")
        if not checks_passed:
            raise AssertionError("未通过验证不得发布")

        async with self.conn.transaction():
            # 幂等重放：候选版本已存在说明上一次发布事务已经提交过（它和 head 前进、
            # job 转 succeeded 在同一条事务里）。此时再插会撞主键，直接当成功返回。
            already = await self.conn.fetchval(
                "select 1 from experiment_revisions where id = $1", candidate_revision_id
            )
            if already:
                return

            head = await self.conn.fetchval(
                "select head_revision_id from experiments where id = $1 FOR UPDATE", experiment_id
            )
            if head is not None and str(head) != str(base_revision):
                raise RevisionConflict(f"head={head} base={base_revision}")

            inserted = await self.conn.execute(
                """insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data, lesson, bindings)
                   select $1, $2, $3, 'ray_optics', $4::jsonb, $7::jsonb, $8::jsonb
                   where exists (
                     select 1 from jobs
                     where id = $5 and lease_token = $6
                       and status = 'running' and lease_until > now()
                   )""",
                candidate_revision_id, experiment_id, base_revision,
                json.dumps(native_data), job_id, lease_token,
                json.dumps(lesson) if lesson else None,
                json.dumps(bindings) if bindings else None,
            )
            if not inserted.endswith("1"):
                raise LeaseLost("no execution right")

            for a in artifacts or []:
                await self.conn.execute(
                    """insert into artifacts (id, revision_id, storage_key, sha256, media_type)
                       values ($1,$2,$3,$4,$5)""",
                    UUID(a["id"]), candidate_revision_id, a["storage_key"], a["sha256"], a["media_type"],
                )

            await self.conn.execute(
                "update experiments set head_revision_id = $2 where id = $1",
                experiment_id, candidate_revision_id,
            )
            await self.conn.execute(
                "update jobs set status='succeeded', stage='packaging', updated_at=now() where id = $1",
                job_id,
            )
