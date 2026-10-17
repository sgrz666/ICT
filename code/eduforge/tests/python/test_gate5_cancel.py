"""§3.5 取消语义与 §6.1 的实验查询接口。

关键区分：取消只作用于未完成任务；已经发布成功的任务不能被"取消"回滚——
否则教师会遇到"我点了取消但学生端还在用新版本"或反过来的不一致。
"""
import asyncio
import tempfile
import uuid
from pathlib import Path

import asyncpg
import httpx
import pgserver
import pytest

from eduforge.api.main import LOCAL_DEV_OWNER, create_app
from eduforge.application.coordinator import STAGES  # noqa: F401  (确保包可导入)
from eduforge.infrastructure.db.migrations import apply_migrations


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-cancel-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


def run(uri, body):
    async def outer():
        app = create_app(uri, Path(tempfile.mkdtemp(prefix="eduforge-art-cancel-")))
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in ("artifacts", "validation_reports", "job_events", "jobs",
                          "experiment_revisions", "experiments"):
                    await c.execute(f"delete from {t}")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                await body(client, app.state.pool)

    asyncio.run(outer())


async def make_experiment(pool, *, published: bool):
    exp_id, head = uuid.uuid4(), uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,$2,$3,$4)",
            exp_id, LOCAL_DEV_OWNER, "optics.convex_lens", head,
        )
        await c.execute(
            "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics','{}')",
            head, exp_id,
        )
        if published:
            second = uuid.uuid4()
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data) values ($1,$2,$3,'ray_optics','{}')",
                second, exp_id, head,
            )
            await c.execute("update experiments set head_revision_id=$2 where id=$1", exp_id, second)
            head = second
    return exp_id, head


async def make_job(pool, *, exp_id, base, status):
    job_id = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                                 idempotency_key, request_hash)
               values ($1,$2,$3,$4,$5,$6,'h')""",
            job_id, LOCAL_DEV_OWNER,
            exp_id, base, status, uuid.uuid4(),
        )
    return job_id


def test_cancel_queued_job_is_cancelled_and_head_untouched(uri):
    async def body(client, pool):
        exp_id, head = await make_experiment(pool, published=False)
        job_id = await make_job(pool, exp_id=exp_id, base=head, status="queued")

        r = await client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "cancelled"

        r = await client.get(f"/api/v1/experiments/{exp_id}")
        assert r.status_code == 200
        # 取消不该动过任何东西：head 还是原来那个，版本数没涨
        assert r.json()["head_revision"] == str(head)
        assert r.json()["revision_count"] == 1

    run(uri, body)


def test_cancel_unknown_job_404(uri):
    async def body(client, _pool):
        r = await client.post(f"/api/v1/jobs/{uuid.uuid4()}/cancel")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "JOB_NOT_FOUND"

    run(uri, body)


def test_cancel_after_success_is_refused_and_does_not_roll_back(uri):
    """控制组语义：已发布成功的任务，取消必须被拒且不回滚 head。"""

    async def body(client, pool):
        exp_id, head_before = await make_experiment(pool, published=False)
        job_id = await make_job(pool, exp_id=exp_id, base=head_before, status="succeeded")

        # 模拟任务已成功发布过：head 前进到新 revision
        async with pool.acquire() as c:
            new_rev = uuid.uuid4()
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data) values ($1,$2,$3,'ray_optics','{}')",
                new_rev, exp_id, head_before,
            )
            await c.execute("update experiments set head_revision_id=$2 where id=$1", exp_id, new_rev)

        r = await client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "ALREADY_SUCCEEDED"

        r = await client.get(f"/api/v1/experiments/{exp_id}")
        assert r.json()["head_revision"] == str(new_rev), "取消把已发布版本回滚了"
        assert r.json()["revision_count"] == 2
        assert r.json()["template_id"] == "optics.convex_lens"

    run(uri, body)


def test_experiment_lookup_404(uri):
    async def body(client, _pool):
        r = await client.get(f"/api/v1/experiments/{uuid.uuid4()}")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "EXPERIMENT_NOT_FOUND"

    run(uri, body)
