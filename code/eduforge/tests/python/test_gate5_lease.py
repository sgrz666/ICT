"""GATE-5：数据库任务与发布规则的实测回归。

用 pgserver 起真实 PostgreSQL（本机没有 Docker Desktop；pip 这条路不需要管理员、
不装系统服务，撤销只需删掉临时目录）。SKIP LOCKED、租约过期接管、旧执行权禁止发布
都是 PostgreSQL 特有语义，SQLite 没有等价物，所以不能用嵌入式替身代替。

连接一律在各用例自己的事件循环内建立与关闭，避免跨循环使用 asyncpg 连接。
"""
import asyncio
import tempfile
import uuid

import asyncpg
import pgserver
import pytest

from eduforge.infrastructure.db.repositories import (
    JOBS_DDL,
    DuplicateIdempotencyKey,
    JobRepository,
    LeaseLost,
    RevisionConflict,
)


@pytest.fixture(scope="module")
def uri():
    data = tempfile.mkdtemp(prefix="eduforge-gate5-")
    server = pgserver.get_server(data, cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


async def fresh(uri):
    """建表并清空，返回一个干净连接。"""
    c = await asyncpg.connect(uri)
    await c.execute(JOBS_DDL)
    await c.execute("delete from experiment_revisions")
    await c.execute("delete from jobs")
    await c.execute("delete from experiments")
    return c


async def new_job(c, *, owner="o", status="queued", lease_token=None, lease_delta=None):
    job_id, exp_id, base_rev = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await c.execute(
        """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                             idempotency_key, request_hash, lease_token, lease_until)
           values ($1,$2,$3,$4,$5,$6,'h',$7,
                   case when $8::int is null then null
                        else now() + make_interval(secs => $8::int) end)""",
        job_id, owner, exp_id, base_rev, status, uuid.uuid4(),
        lease_token, lease_delta,
    )
    return job_id, exp_id, base_rev


def test_server_is_real_postgres_with_needed_semantics(uri):
    async def inner():
        c = await fresh(uri)
        try:
            return await c.fetchval("select version()")
        finally:
            await c.close()

    v = asyncio.run(inner())
    assert "PostgreSQL" in v
    # 断言的是版本足以支持 SKIP LOCKED（9.5+）与 make_interval，而不是"能连上"
    assert int(v.split()[1].split(".")[0]) >= 12


def test_idempotency_control_group(uri):
    """控制组：同一幂等键 + 同一请求体 → 只有一个任务，且返回同一 id。"""

    async def inner():
        c = await fresh(uri)
        try:
            repo = JobRepository(c)
            owner, key = "t1", uuid.uuid4()
            exp, base, prompt = uuid.uuid4(), uuid.uuid4(), "把焦距改成 15 厘米"
            a = await repo.create_job(
                job_id=uuid.uuid4(), owner_id=owner, experiment_id=exp,
                base_revision=base, prompt=prompt, idempotency_key=key,
            )
            b = await repo.create_job(
                job_id=uuid.uuid4(), owner_id=owner, experiment_id=exp,
                base_revision=base, prompt=prompt, idempotency_key=key,
            )
            n = await c.fetchval("select count(*) from jobs")
            return a["id"], b["id"], n
        finally:
            await c.close()

    id_a, id_b, n = asyncio.run(inner())
    assert id_a == id_b
    assert n == 1


def test_same_key_different_body_rejected(uri):
    async def inner():
        c = await fresh(uri)
        try:
            repo = JobRepository(c)
            owner, key = "t2", uuid.uuid4()
            exp, base = uuid.uuid4(), uuid.uuid4()
            await repo.create_job(
                job_id=uuid.uuid4(), owner_id=owner, experiment_id=exp,
                base_revision=base, prompt="焦距 15", idempotency_key=key,
            )
            with pytest.raises(DuplicateIdempotencyKey):
                await repo.create_job(
                    job_id=uuid.uuid4(), owner_id=owner, experiment_id=exp,
                    base_revision=base, prompt="焦距 30", idempotency_key=key,
                )
        finally:
            await c.close()

    asyncio.run(inner())


def test_two_workers_never_claim_same_live_lease(uri):
    """两个事务重叠时，SKIP LOCKED 必须让它们各拿不同的行。"""

    async def inner():
        a, b = await fresh(uri), await asyncpg.connect(uri)
        try:
            for _ in range(3):
                await a.execute(
                    """insert into jobs (id, owner_id, experiment_id, base_revision,
                                         status, idempotency_key, request_hash)
                       values ($1,'w',$2,$3,'queued',$4,'h')""",
                    uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(),
                )
            ta, tb = a.transaction(), b.transaction()
            await ta.start()
            await tb.start()
            first = await JobRepository(a).claim("tok-A")
            second = await JobRepository(b).claim("tok-B")
            await ta.commit()
            await tb.commit()
            return first["id"], second["id"]
        finally:
            await a.close()
            await b.close()

    id_a, id_b = asyncio.run(inner())
    assert id_a is not None and id_b is not None
    assert id_a != id_b, "两个 Worker 领到了同一行"


def test_stale_lease_reclaimed_and_old_token_cannot_publish(uri):
    """过期租约可被接管；旧 token 既改不动阶段也不能发布，head 不被污染。"""

    async def inner():
        c = await fresh(uri)
        try:
            job_id, exp_id, base_rev, cand = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await c.execute(
                "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,'o','optics.convex_lens',$2)",
                exp_id, base_rev,
            )
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics','{}')",
                base_rev, exp_id,
            )
            await c.execute(
                """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                                     idempotency_key, request_hash, lease_token, lease_until)
                   values ($1,'o',$2,$3,'running',$4,'h','old-token', now() - interval '1 second')""",
                job_id, exp_id, base_rev, uuid.uuid4(),
            )
            repo = JobRepository(c)

            claimed = await repo.claim("new-token")
            assert claimed is not None and claimed["id"] == job_id
            assert claimed["lease_token"] == "new-token"

            assert await repo.set_stage(job_id, "old-token", "building") is False
            assert await repo.renew_lease(job_id, "old-token") is False

            with pytest.raises(LeaseLost):
                await repo.publish(
                    job_id=job_id, lease_token="old-token", experiment_id=exp_id,
                    base_revision=base_rev, candidate_revision_id=cand,
                    native_data={"version": 5}, checks_passed=True,
                )
            head = await c.fetchval("select head_revision_id from experiments where id=$1", exp_id)
            assert str(head) == str(base_rev), "旧执行权把 head 改掉了"
        finally:
            await c.close()

    asyncio.run(inner())


def test_publish_gates(uri):
    """验证未过 / 已取消 / 版本冲突都不得发布；正常路径 head 前进且任务 succeeded。"""

    async def inner():
        c = await fresh(uri)
        try:
            exp_id, base_rev, cand, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await c.execute(
                "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,'o','t',$2)",
                exp_id, base_rev,
            )
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics','{}')",
                base_rev, exp_id,
            )
            await c.execute(
                """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                                     idempotency_key, request_hash, lease_token, lease_until)
                   values ($1,'o',$2,$3,'running',$4,'h','tok', now() + interval '60 seconds')""",
                job_id, exp_id, base_rev, uuid.uuid4(),
            )
            repo = JobRepository(c)
            common = dict(job_id=job_id, lease_token="tok", experiment_id=exp_id,
                          base_revision=base_rev, candidate_revision_id=cand)

            with pytest.raises(AssertionError):
                await repo.publish(**common, native_data={}, checks_passed=False)
            with pytest.raises(LeaseLost):
                await repo.publish(**common, native_data={}, checks_passed=True, cancelled=True)

            other = uuid.uuid4()
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics','{}')",
                other, exp_id,
            )
            await c.execute("update experiments set head_revision_id=$2 where id=$1", exp_id, other)
            with pytest.raises(RevisionConflict):
                await repo.publish(**common, native_data={}, checks_passed=True)

            await c.execute("update experiments set head_revision_id=$2 where id=$1", exp_id, base_rev)
            await repo.publish(**common, checks_passed=True, native_data={"version": 5})
            assert str(await c.fetchval("select head_revision_id from experiments where id=$1", exp_id)) == str(cand)
            assert await c.fetchval("select status from jobs where id=$1", job_id) == "succeeded"
        finally:
            await c.close()

    asyncio.run(inner())
