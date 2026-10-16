"""GATE-5 的恢复项：Worker 崩在中途后，新 Worker 必须从保存的 stage 接着走，
而不是从头再跑一遍。这是原计划里"待证：杀进程重启后任务从保存的 stage 恢复"那条。
"""
import asyncio
import time
import uuid

import asyncpg
import pgserver
import pytest

from eduforge.application.coordinator import STAGES, Coordinator
from eduforge.infrastructure.db.repositories import JOBS_DDL, JobRepository
from eduforge.worker.main import SimulatedCrash, Worker


@pytest.fixture(scope="module")
def uri():
    import tempfile
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-recover-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


async def seed(uri):
    c = await asyncpg.connect(uri)
    await c.execute(JOBS_DDL)
    await c.execute("delete from job_events")
    await c.execute("delete from jobs")
    job_id = uuid.uuid4()
    await c.execute(
        """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                             idempotency_key, request_hash)
           values ($1,'o',$2,$3,'queued',$4,'h')""",
        job_id, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(),
    )
    return c, job_id


def test_worker_resumes_from_saved_stage_after_crash(uri):
    async def inner():
        c, job_id = await seed(uri)
        calls: list[str] = []

        def make_step(name):
            async def step(_jid):
                calls.append(name)
                return {"ok": True}
            return step

        steps = {s: make_step(s) for s in STAGES}

        # Worker A：短租约，跑到 building 之前崩掉
        repo_a = JobRepository(c)
        coord_a = Coordinator(repo=repo_a, steps=steps)
        w_a = Worker(repo=repo_a, coordinator=coord_a, lease_seconds=1)
        with pytest.raises(SimulatedCrash):
            await w_a.run_once(crash_before="building")
        assert calls == ["planning", "editing"], f"崩溃前只该走完前两档，实际 {calls}"

        # 租约过期，等价于进程被杀且没再续租
        await asyncio.sleep(1.3)

        # Worker B：接管，必须从 building 接着走，不能重跑 planning/editing
        del calls[:]
        repo_b = JobRepository(c)
        coord_b = Coordinator(repo=repo_b, steps=steps)
        w_b = Worker(repo=repo_b, coordinator=coord_b, lease_seconds=90)
        result = await w_b.run_once()

        events = await repo_b.events(job_id)
        starts = [e["stage"] for e in events if e["event_type"] == "stage_start"]
        status = await c.fetchval("select status from jobs where id=$1", job_id)
        await c.close()
        return calls, starts, result, status

    all_calls, starts, result, status = asyncio.run(inner())

    # B 单独看：从 building 起，共 3 档
    assert all_calls == ["building", "validating", "packaging"], all_calls
    # 全程看：planning/editing 各只启动过一次，building 因崩溃重跑一次（at-least-once）
    assert starts.count("planning") == 1
    assert starts.count("editing") == 1
    assert starts.count("building") == 2
    assert starts.count("validating") == 1
    assert starts.count("packaging") == 1
    assert result["last_stage"] == "packaging"
    assert status == "running"  # 未走发布，状态仍是 running


def test_idle_worker_claims_nothing(uri):
    """没有可领取的任务时 run_once 返回 None，不抛错也不空转占租约。"""

    async def noop(_job_id):
        return {}

    async def inner():
        c, _ = await seed(uri)
        await c.execute("update jobs set status='succeeded'")
        repo = JobRepository(c)
        coord = Coordinator(repo=repo, steps={s: noop for s in STAGES})
        w = Worker(repo=repo, coordinator=coord)
        out = await w.run_once()
        await c.close()
        return out

    assert asyncio.run(inner()) is None
