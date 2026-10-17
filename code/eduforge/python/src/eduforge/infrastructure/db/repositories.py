"""任务与版本的持久层。

只用 asyncpg 裸 SQL：计划 §4.8 的领取语义依赖 PostgreSQL 的
`FOR UPDATE SKIP LOCKED`，这正是要验的东西，套 ORM 反而遮住它。
"""
from __future__ import annotations

import hashlib
import json
import uuid
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
    -- 每次重新领取都递增 attempt：这是「第几次跑」的唯一记账处。
    -- 不写它，崩溃重跑就没有痕迹，也就无法设定重试上限。
    attempt = job.attempt + 1,
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


# 候选版本与产物 id 由 job_id 派生，不用随机 uuid：
# 崩在 packaging 里重来时必须落在同一批 id 上，否则重跑会插出第二个候选版本、
# 或把同一份字节登记成两个产物。Worker 与工具层共用这一条派生规则。
ID_NAMESPACE = UUID("6b1c9df8-7f6a-4f0e-9b9f-4b8a9c1edf01")


def derived_id(job_id: UUID, kind: str) -> UUID:
    return uuid.uuid5(ID_NAMESPACE, f"{job_id}:{kind}")


# 候选与候选派生物（发布版本、产物登记）的 id 一律带内容哈希：
# 同一份内容重跑落在同一个 id 上（幂等），内容变了就是新版本（连续编辑链）。
# 只按 job_id 派生会让同一个 job 的第二次编辑撞主键，把「先改 A 再改 B」
# 悄悄变成「交付 A」。
def candidate_id_for(job_id: UUID) -> UUID:
    """一个 job 只有一个工作态候选，id 稳定，不随内容变化。"""
    return derived_id(job_id, "candidate")


def revision_id_for(job_id: UUID, content_hash: str) -> UUID:
    """发布出去的版本 id：由候选内容哈希派生。"""
    return derived_id(job_id, f"revision:{content_hash}")


def artifact_id_for(job_id: UUID, name: str, digest: str) -> UUID:
    return derived_id(job_id, f"artifact:{name}:{digest}")


class DuplicateIdempotencyKey(Exception):
    """同一个幂等键配了不同请求内容。"""


class LeaseLost(Exception):
    """执行权已不在自己手上，禁止继续推进或发布。"""


class RevisionConflict(Exception):
    """教师在任务执行期间产生了其他版本。"""


class OwnershipConflict(Exception):
    """任务身份与资源归属对不上。

    这不是并发问题，是授权问题：拿别人的 job 或别人的实验来发布，
    哪怕租约有效也必须拒——发布事务是唯一还能拦住它的地方。
    """


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
        return (await self.renew_and_check(job_id, lease_token, lease_seconds)) == "ok"

    async def renew_and_check(
        self, job_id: UUID, lease_token: str, lease_seconds: int = 90
    ) -> str:
        """续租并回报执行权状态：`ok` / `cancelled` / `stolen` / `expired` / `lost` / `missing`。

        三条硬规矩（Gate B §B.1–B.2）：
        - 只有 `status='running'` 且 `lease_token` 一致才续，别的状态一律不给执行权；
        - **已过期不允许续成合法**（`lease_until > now()` 必须在续之前成立），
          否则「先让租约睡过期、再自己续回来」就绕过了抢占语义；
        - 取消不是失败：它单独回报，让 Worker 停止新动作而不是报错重试。
        """
        async with self.conn.transaction():
            row = await self.conn.fetchrow(
                "select status, lease_token, lease_until from jobs where id = $1 for update",
                job_id,
            )
            if row is None:
                return "missing"
            if row["status"] == "cancelled":
                return "cancelled"
            if row["status"] != "running":
                return "lost"
            if row["lease_token"] != lease_token:
                return "stolen"
            if row["lease_until"] is None or row["lease_until"] <= datetime.now(row["lease_until"].tzinfo):
                return "expired"
            await self.conn.execute(
                """update jobs set lease_until = now() + make_interval(secs => $2), updated_at = now()
                   where id = $1""",
                job_id, float(lease_seconds),
            )
            return "ok"

    async def retry_later(
        self, job_id: UUID, lease_token: str, *, delay_seconds: float, error_code: str
    ) -> str | None:
        """可重试失败：回到 `queued` 并推迟 `next_run_at`（有限退避，不是无界重跑）。

        已成功的任务不被改回排队——那等于把发布出去的版本重新变成待办。
        """
        row = await self.conn.fetchrow(
            """update jobs
                  set status = case when status = 'succeeded' then status else 'queued' end,
                      next_run_at = now() + make_interval(secs => $3),
                      error_code = case when status = 'succeeded' then error_code else $4 end,
                      lease_token = NULL, lease_until = NULL, updated_at = now()
                where id = $1 and lease_token = $2 and status = 'running'
                returning status""",
            job_id, lease_token, float(delay_seconds), error_code,
        )
        return row["status"] if row else None

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
        """进度事件按 (job_id, sequence) 递增追加。恢复执行靠它判断走到哪一步。

        序号必须在事务里、拿着 job 行锁算：以前 `max(sequence)+1` 与 insert 是两条
        独立语句，同一个 job 并发追加（心跳、工具事件、阶段事件）会撞出重复序列，
        主键冲突直接吃掉一条证据。
        """
        async with self.conn.transaction():
            await self.conn.execute("select 1 from jobs where id = $1 for update", job_id)
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
        close_job: bool = True,
        expected_native_sha256: str | None = None,
    ) -> None:
        """§3.5 的发布事务：执行权、取消、验证、基础版本四道闸门后写版本。

        必须在同一个事务里插入版本、文件索引并推进 head——分开写会出现
        head 指向不存在版本的中闲状态。artifacts 外键指向本事务插入的
        experiment_revisions 行，所以文件索引只能在发布时登记。

        close_job=False 时只提交版本、不把 job 置为 succeeded：智能体的连续编辑
        要在同一个 job 里提交多个版本，job 的终态由最后一次发布负责。
        """
        if cancelled:
            raise LeaseLost("cancelled")
        if not checks_passed:
            raise AssertionError("未通过验证不得发布")

        async with self.conn.transaction():
            # 幂等重放：候选版本已存在说明上一次发布事务已经提交过。
            # 但「UUID 已存在」本身不构成成功证据——必须核对它确实属于这个 job、
            # 这个实验、这个基础版本，且登记的字节就是本次要交付的那份，
            # 否则第二个 Worker 换了内容也能顶着同一个 id 宣布「已发布」。
            already = await self.conn.fetchrow(
                "select experiment_id, parent_id from experiment_revisions where id = $1",
                candidate_revision_id,
            )
            if already is not None:
                if str(already["experiment_id"]) != str(experiment_id):
                    raise OwnershipConflict(
                        f"版本 {candidate_revision_id} 属于实验 {already['experiment_id']}，不是 {experiment_id}"
                    )
                if str(already["parent_id"] or "") != str(base_revision):
                    raise RevisionConflict(
                        f"版本 {candidate_revision_id} 的父版本是 {already['parent_id']}，不是 {base_revision}"
                    )
                await self._assert_same_publication(
                    job_id, candidate_revision_id, expected_native_sha256
                )
                return

            owner_row = await self.conn.fetchrow(
                """select e.owner_id as exp_owner, j.owner_id as job_owner,
                          e.head_revision_id as head
                   from experiments e
                   left join jobs j on j.id = $2
                   where e.id = $1
                   for update of e""",
                experiment_id, job_id,
            )
            if owner_row is None:
                raise OwnershipConflict(f"实验 {experiment_id} 不存在")
            if owner_row["job_owner"] is None or str(owner_row["exp_owner"]) != str(owner_row["job_owner"]):
                raise OwnershipConflict(
                    f"任务 {job_id} 的身份 {owner_row['job_owner']} 与实验归属 {owner_row['exp_owner']} 不一致"
                )
            head = owner_row["head"]
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
            if close_job:
                await self.conn.execute(
                    "update jobs set status='succeeded', stage='packaging', updated_at=now() where id = $1",
                    job_id,
                )

    async def _assert_same_publication(
        self, job_id: UUID, candidate_revision_id: UUID, expected_native_sha256: str | None
    ) -> None:
        """重放已存在的发布时的核对。

        「同一个 UUID 再发一次」只有在**内容也相同**时才是幂等重放；否则它就是
        两个不同的交付物在抢同一个版本 id，必须报错而不是静默返回成功。
        """
        job_cand = await self.conn.fetchval(
            "select candidate_revision_id from jobs where id = $1", job_id
        )
        if job_cand is not None and str(job_cand) != str(candidate_revision_id):
            raise RevisionConflict(
                f"任务 {job_id} 登记的候选是 {job_cand}，与要重放的 {candidate_revision_id} 不是同一份"
            )
        if expected_native_sha256 is None:
            return
        recorded = await self.conn.fetchval(
            "select sha256 from artifacts where revision_id = $1 "
            "and storage_key like '%native.json' order by created_at",
            candidate_revision_id,
        )
        if recorded is None:
            raise RevisionConflict(f"版本 {candidate_revision_id} 没有登记原生场景产物，不能当作发布成功")
        if recorded != expected_native_sha256:
            raise RevisionConflict(
                f"交付字节不一致：已登记 {recorded[:12]}…，本次要发 {expected_native_sha256[:12]}…"
            )
