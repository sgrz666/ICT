"""§6.1 版本回滚语义接口测试。

回滚（把 head 指回历史 revision）是教师界面核心能力：
- 只有属于本实验的历史版本可作为目标；
- 有运行/排队中任务时拒绝回滚（409 ACTIVE_JOB_RUNNING），杜绝并发状态污染；
- 回滚改变 experiments.head_revision_id，但保留全量版本历史。
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


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-rollback-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


def run(uri, body):
    async def outer():
        app = create_app(uri, Path(tempfile.mkdtemp(prefix="eduforge-art-rollback-")))
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in ("artifacts", "validation_reports", "job_events", "jobs",
                          "experiment_revisions", "experiments"):
                    await c.execute(f"delete from {t}")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                await body(client, app.state.pool)

    asyncio.run(outer())


async def make_experiment_two_revs(pool):
    exp_id = uuid.uuid4()
    rev1 = uuid.uuid4()
    rev2 = uuid.uuid4()
    async with pool.acquire() as c:
        await c.execute(
            "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,$2,$3,$4)",
            exp_id, LOCAL_DEV_OWNER, "optics.convex_lens", rev2,
        )
        await c.execute(
            "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics','{}')",
            rev1, exp_id,
        )
        await c.execute(
            "insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data) values ($1,$2,$3,'ray_optics','{}')",
            rev2, exp_id, rev1,
        )
    return exp_id, rev1, rev2


def test_rollback_to_base_revision_updates_head(uri):
    async def body(client, pool):
        exp_id, rev1, rev2 = await make_experiment_two_revs(pool)

        # 初始状态：head 是 rev2
        r = await client.get(f"/api/v1/experiments/{exp_id}")
        assert r.status_code == 200
        assert r.json()["head_revision"] == str(rev2)
        assert r.json()["revision_count"] == 2

        # 回滚到 rev1
        r = await client.post(
            f"/api/v1/experiments/{exp_id}/rollback",
            json={"target_revision_id": str(rev1)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["head_revision"] == str(rev1)
        assert r.json()["revision_count"] == 2

        # 再次确认查询接口反映出 head 迁移
        r = await client.get(f"/api/v1/experiments/{exp_id}")
        assert r.status_code == 200
        assert r.json()["head_revision"] == str(rev1)

    run(uri, body)


def test_rollback_unknown_experiment_404(uri):
    async def body(client, pool):
        r = await client.post(
            f"/api/v1/experiments/{uuid.uuid4()}/rollback",
            json={"target_revision_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "EXPERIMENT_NOT_FOUND"

    run(uri, body)


def test_rollback_unknown_revision_404(uri):
    async def body(client, pool):
        exp_id, rev1, rev2 = await make_experiment_two_revs(pool)
        r = await client.post(
            f"/api/v1/experiments/{exp_id}/rollback",
            json={"target_revision_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "REVISION_NOT_FOUND"

    run(uri, body)


def test_rollback_foreign_revision_404(uri):
    async def body(client, pool):
        exp_id1, rev1_1, rev1_2 = await make_experiment_two_revs(pool)
        exp_id2, rev2_1, rev2_2 = await make_experiment_two_revs(pool)

        # 试图将 exp1 回滚到属于 exp2 的 revision
        r = await client.post(
            f"/api/v1/experiments/{exp_id1}/rollback",
            json={"target_revision_id": str(rev2_1)},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "REVISION_NOT_FOUND"

        # exp1 的 head 仍未改变
        r = await client.get(f"/api/v1/experiments/{exp_id1}")
        assert r.json()["head_revision"] == str(rev1_2)

    run(uri, body)


def test_rollback_active_job_conflict_409(uri):
    async def body(client, pool):
        exp_id, rev1, rev2 = await make_experiment_two_revs(pool)

        # 插入一个 running 状态的任务
        async with pool.acquire() as c:
            await c.execute(
                """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                                     idempotency_key, request_hash)
                   values ($1,$2,$3,$4,'running',$5,'h')""",
                uuid.uuid4(), LOCAL_DEV_OWNER,
                exp_id, rev2, uuid.uuid4(),
            )

        r = await client.post(
            f"/api/v1/experiments/{exp_id}/rollback",
            json={"target_revision_id": str(rev1)},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "ACTIVE_JOB_RUNNING"

        # head 仍保持未被污染
        r = await client.get(f"/api/v1/experiments/{exp_id}")
        assert r.json()["head_revision"] == str(rev2)

    run(uri, body)
