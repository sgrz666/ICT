"""Gate B 的验收：执行权、重试、取消、幂等与归属。

这些用例对应指令 §2 Gate B 的通过条件，逐条要有可跑的证据：

1. 长于租约时长的模型调用能够续租（并带**控制组**：不给池就没有心跳，租约照旧过期）；
2. 丢失执行权后停止新工具动作，且不能发布；
3. 取消后不发布；
4. 双 Worker 不双发布；
5. 跨用户不可查 / 改 / 下载他人资源，生产可关闭固定开发身份；
6. 重复执行不重复副作用（`attempt` 记账 + 有限退避 + 事件序号唯一 + 发布幂等核对字节）。

故障注入直接打在数据库状态上（改 `lease_token`、把 job 置成 `cancelled`），
因为要证的就是「SQL 里那几道守卫」，不是 Python 里的 if。
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path

import asyncpg
import httpx
import pgserver
import pytest

from eduforge.api.main import create_app
from eduforge.application.job_service import JobService
from eduforge.application.publication import Publisher
from eduforge.domain.contracts import EditProposal, SetParameter
from eduforge.domain.errors import ConflictError, LeaseExpiredError, NotFoundError
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    BuildPackageInput,
    InspectSceneInput,
    JobContext,
    OpenExperimentInput,
    RunValidationInput,
)
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.catalog import load_native
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.migrations import apply_migrations
from eduforge.infrastructure.db.repositories import (
    JobRepository,
    RevisionConflict,
    candidate_id_for,
    revision_id_for,
)
from eduforge.worker.lease import LeaseManager
from eduforge.worker.steps import Chain, StaticPlanner, make_worker

OWNER_A = "teacher-a"
OWNER_B = "teacher-b"
TABLES = (
    "experiment_candidates", "artifacts", "validation_reports", "job_events",
    "jobs", "experiment_revisions", "experiments",
)


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-gateB-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture
def art_dir():
    return Path(tempfile.mkdtemp(prefix="eduforge-gateB-art-"))


async def _schema(c):
    await apply_migrations(c)
    for t in TABLES:
        await c.execute(f"delete from {t}")


async def _seed(c, *, owner: str = OWNER_A, prompt="把焦距改成 15cm", queued: bool = True):
    exp_id, rev_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await c.execute(
        "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,$2,'optics.convex_lens',$3)",
        exp_id, owner, rev_id,
    )
    await c.execute(
        "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics',$3::jsonb)",
        rev_id, exp_id, json.dumps(load_native("optics.convex_lens")),
    )
    await c.execute(
        """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                             idempotency_key, request_hash)
           values ($1,$2,$3,$4,$5,$6,$7,'h')""",
        job_id, owner, exp_id, rev_id, prompt, "queued" if queued else "running", uuid.uuid4(),
    )
    return exp_id, rev_id, job_id


def _focal_proposal(cm: float = 15) -> EditProposal:
    return EditProposal(
        route="config",
        operations=[SetParameter(entity_id="lens_1", parameter="focal_length_cm", value=cm)],
    )


class SlowPlanner:
    """链路验证用的慢规划器：只用来把执行时间拉长到超过租约，不作任何能力证据。"""

    def __init__(self, proposal: EditProposal, delay: float) -> None:
        self.proposal = proposal
        self.delay = delay

    async def plan(self, request):
        await asyncio.sleep(self.delay)
        return self.proposal


def test_heartbeat_keeps_lease_and_control_group_proves_it(uri, art_dir, engine_url):
    """续租是真起作用的：同一个慢任务，有心跳时别人领不走，没心跳时立刻被抢走。

    控制组不是装饰——没有它，「心跳保住了租约」这句话和「任务本来就够快」无法区分。
    """
    lease = 2.0
    delay = 3.5

    async def run(with_pool: bool):
        c = await asyncpg.connect(uri)
        pool = await asyncpg.create_pool(uri, min_size=1, max_size=3) if with_pool else None
        try:
            await _schema(c)
            exp_id, rev_id, job_id = await _seed(c)
            worker = make_worker(
                c, engine_url=engine_url, artifact_dir=art_dir,
                planner=SlowPlanner(_focal_proposal(), delay), lease_seconds=int(lease),
                pool=pool, heartbeat_seconds=0.4,
            )
            stolen = {"count": 0}

            async def claimer():
                other = await asyncpg.connect(uri)
                try:
                    repo = JobRepository(other)
                    deadline = time.monotonic() + delay
                    while time.monotonic() < deadline:
                        got = await repo.claim(f"thief-{uuid.uuid4().hex[:6]}", 60)
                        if got is not None and str(got["id"]) == str(job_id):
                            stolen["count"] += 1
                            return
                        await asyncio.sleep(0.3)
                finally:
                    await other.close()

            result, _ = await asyncio.gather(worker.run_once(), claimer())
            renewals = getattr(getattr(worker, "last_guard", None), "renewals", 0)
            attempt = await c.fetchval("select attempt from jobs where id = $1", job_id)
            status = await c.fetchval("select status from jobs where id = $1", job_id)
            return {"result": result, "stolen": stolen["count"], "renewals": renewals,
                    "attempt": attempt, "status": status}
        finally:
            await c.close()
            if pool is not None:
                await pool.close()

    with_heartbeat = asyncio.run(run(True))
    without = asyncio.run(run(False))

    assert with_heartbeat["stolen"] == 0, with_heartbeat
    assert with_heartbeat["renewals"] >= 2, "心跳至少续过两次，否则这条证据不成立"
    assert with_heartbeat["result"].get("last_stage") == "packaging", with_heartbeat["result"]
    # 控制组：没有池就没有心跳，租约在执行中途到期，别的 Worker 能把它领走
    assert without["stolen"] >= 1, without
    assert without["attempt"] >= 2, without


def test_stolen_lease_blocks_writes_and_publish(uri, art_dir, engine_url):
    """执行权被抢走后：新的工具动作写不进去，发布当场被拒。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, rev_id, job_id = await _seed(c)
            token = uuid.uuid4().hex
            await c.execute(
                """update jobs set status='running', lease_token=$2,
                          lease_until = now() + interval '300 seconds' where id=$1""",
                job_id, token,
            )
            job = JobContext(job_id=job_id, owner_id=OWNER_A, lease_token=token,
                             experiment_id=exp_id, base_revision=rev_id)
            guard = LeaseManager(JobRepository(c), job_id, token)
            assert await guard.beat() == "ok"
            service = ExperimentToolService(
                engine_client=EngineClient(engine_url), conn=c, artifact_dir=art_dir,
                job=job, execution_check=guard.check_active,
            )
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(rev_id), template_id="optics.convex_lens"))
            await service.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))

            # 抢走执行权（模拟前一个 Worker 心跳断掉后被接管）
            await c.execute(
                """update jobs set lease_token=$2, lease_until = now() + interval '300 seconds'
                   where id=$1""", job_id, "thief-token",
            )
            assert await guard.beat() == "stolen"
            with pytest.raises(LeaseExpiredError) as exc:
                await service.apply_scene_patch(ApplyScenePatchInput(
                    experiment_id=str(exp_id),
                    edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 20.0}]))
            assert exc.value.code == "LEASE_LOST"
            insp = await service.inspect_scene(InspectSceneInput(experiment_id=str(exp_id)))
            assert insp.parameters["focal_length_cm"] == 15.0, "丢权之后不该有第二次写入落进候选"

            # 旧 Worker 拿同一候选去发布：事务必须因为 lease_token 不再匹配而拒
            val = await service.run_validation(RunValidationInput(experiment_id=str(exp_id)))
            assert val.passed is True
            built = await service.build_package(BuildPackageInput(
                experiment_id=str(exp_id), export_offline_zip=False))
            state = await service.candidates.load()
            with pytest.raises(Exception) as publish_exc:
                await Publisher(c).publish(
                    job_id=job_id, lease_token=token, experiment_id=exp_id,
                    base_revision=rev_id, candidate_revision_id=uuid.UUID(built.candidate_revision_id),
                    native_data=state.native_data, report_verdict="passed",
                    artifacts=built.artifacts, expected_native_sha256=built.sha256,
                )
            assert type(publish_exc.value).__name__ in ("LeaseLost", "AssertionError"), publish_exc.value
            assert await c.fetchval("select count(*) from experiment_revisions") == 1
        finally:
            await c.close()

    asyncio.run(go())


def test_cancelled_job_stops_the_chain_and_cannot_publish(uri, art_dir, engine_url):
    """教师取消之后：守护器回报 cancelled，发布事务同样进不去。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, rev_id, job_id = await _seed(c)
            token = uuid.uuid4().hex
            await c.execute(
                "update jobs set status='running', lease_token=$2, lease_until=now()+interval '300 seconds' where id=$1",
                job_id, token,
            )
            guard = LeaseManager(JobRepository(c), job_id, token)
            assert await guard.beat() == "ok"
            await c.execute("update jobs set status='cancelled' where id=$1", job_id)
            assert await guard.beat() == "cancelled"
            with pytest.raises(LeaseExpiredError) as exc:
                guard.check_active()
            assert exc.value.code == "JOB_CANCELLED"

            # 即使绕过守护器直接调发布事务，SQL 里的执行权守卫也拦得住
            chain = Chain(conn=c, engine=EngineClient(engine_url), artifact_dir=art_dir,
                          planner=StaticPlanner(_focal_proposal()), lease_token=token)
            base = await chain._base(job_id)
            with pytest.raises(Exception) as pub_exc:
                await Publisher(c).publish(
                    job_id=job_id, lease_token=token, experiment_id=base["experiment_id"],
                    base_revision=base["base_revision"], candidate_revision_id=uuid.uuid4(),
                    native_data=base["native"], report_verdict="passed",
                    artifacts=[{"id": str(uuid.uuid4()), "storage_key": "x/native.json",
                                "sha256": "deadbeef", "media_type": "application/json"}],
                )
            assert type(pub_exc.value).__name__ in ("LeaseLost", "OwnershipConflict"), pub_exc.value
            assert await c.fetchval("select count(*) from experiment_revisions") == 1
        finally:
            await c.close()

    asyncio.run(go())


def test_attempt_is_accounted_and_backoff_bounds_retries(uri):
    """重新领取必须把 attempt 记上去；可重试失败退回队列并推迟 next_run_at。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            _exp, _rev, job_id = await _seed(c)
            repo = JobRepository(c)
            first = await repo.claim("w-1", 1)
            assert str(first["id"]) == str(job_id)
            assert int(first["attempt"]) == 1, first["attempt"]
            # 让租约到期，另一个 Worker 才能接管
            await c.execute("update jobs set lease_until = now() - interval '1 second' where id=$1", job_id)
            second = await repo.claim("w-2", 1)
            assert second is not None and int(second["attempt"]) == 2, second["attempt"]

            deferred = await repo.retry_later(job_id, "w-2", delay_seconds=30, error_code="RETRY_EngineError")
            assert deferred == "queued"
            row = await c.fetchrow("select status, error_code, next_run_at > now() as future from jobs where id=$1", job_id)
            assert row["error_code"] == "RETRY_EngineError" and row["future"] is True, dict(row)
            # 退避期内不得被再次领取
            assert await repo.claim("w-3", 1) is None

            # 超过重试上限：run_once 终态化，不再无限重跑。
            # 前一个 job 推到一小时之后，保证这次领取拿到的就是 job2
            await c.execute(
                "update jobs set next_run_at = now() + interval '1 hour' where id=$1", job_id
            )
            _exp2, _rev2, job2 = await _seed(c)
            await c.execute("update jobs set attempt = 9 where id=$1", job2)
            worker = make_worker(c, engine_url="http://127.0.0.1:1",
                                 artifact_dir=Path(tempfile.mkdtemp()),
                                 planner=StaticPlanner(_focal_proposal()), lease_seconds=60)
            out = await worker.run_once()
            assert out["failed"] == "MAX_ATTEMPTS_EXCEEDED", out
            assert await c.fetchval("select status from jobs where id=$1", job2) == "failed"
        finally:
            await c.close()

    asyncio.run(go())


def test_event_sequence_is_unique_under_concurrent_append(uri):
    """同一个 job 并发追加事件：序号不能撞（撞了就是主键冲突，丢一条证据）。

    用的是**连接池**——真实场景里并发追加来自不同连接（心跳、阶段事件、工具事件），
    单条 asyncpg 连接本来就不允许并发查询，拿它测并发只会测到客户端的排队行为。
    """

    async def go():
        pool = await asyncpg.create_pool(uri, min_size=4, max_size=8)
        try:
            async with pool.acquire() as c:
                await _schema(c)
                _exp, _rev, job_id = await _seed(c)

            async def one(i: int) -> int:
                async with pool.acquire() as cc:
                    return await JobRepository(cc).append_event(
                        job_id, stage="planning", event_type="tool_call", payload={"i": i}
                    )

            seqs = await asyncio.gather(*[one(i) for i in range(12)])
            assert sorted(seqs) == list(range(1, 13)), sorted(seqs)
            async with pool.acquire() as c:
                count = await c.fetchval("select count(*) from job_events where job_id=$1", job_id)
            assert int(count) == 12
        finally:
            await pool.close()

    asyncio.run(go())


def test_publish_replay_checks_the_bytes(uri, art_dir, engine_url):
    """同一个版本 id 再发一次：内容必须一致，否则不是幂等重放而是抢 id。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, rev_id, job_id = await _seed(c)
            token = uuid.uuid4().hex
            await c.execute(
                "update jobs set status='running', lease_token=$2, lease_until=now()+interval '300 seconds' where id=$1",
                job_id, token,
            )
            job = JobContext(job_id=job_id, owner_id=OWNER_A, lease_token=token,
                             experiment_id=exp_id, base_revision=rev_id)
            service = ExperimentToolService(
                engine_client=EngineClient(engine_url), conn=c, artifact_dir=art_dir, job=job,
            )
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(rev_id), template_id="optics.convex_lens"))
            await service.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))
            built = await service.build_package(BuildPackageInput(
                experiment_id=str(exp_id), export_offline_zip=False))
            state = await service.candidates.load()

            # 同一份内容再发一次：幂等重放，不报错、不多出版本
            await Publisher(c).publish(
                job_id=job_id, lease_token=token, experiment_id=exp_id, base_revision=rev_id,
                candidate_revision_id=uuid.UUID(built.candidate_revision_id),
                native_data=state.native_data, report_verdict="passed", artifacts=built.artifacts,
                expected_native_sha256=built.sha256,
            )
            assert await c.fetchval("select count(*) from experiment_revisions") == 2

            # 换一个内容抢同一个 id：必须拒
            other = json.loads(json.dumps(state.native_data))
            lens = next(o for o in other["objs"] if o.get("type") == "IdealLens")
            lens["focalLength"] = 400
            with pytest.raises(RevisionConflict):
                await Publisher(c).publish(
                    job_id=job_id, lease_token=token, experiment_id=exp_id, base_revision=rev_id,
                    candidate_revision_id=uuid.UUID(built.candidate_revision_id),
                    native_data=other, report_verdict="passed",
                    artifacts=built.artifacts,
                    expected_native_sha256="0000000000000000000000000000000000000000000000000000000000000000",
                )
        finally:
            await c.close()

    asyncio.run(go())


def test_publish_refuses_foreign_identity(uri, art_dir, engine_url):
    """拿别人的 job 发别人的实验：归属不符，事务直接拒。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_a, rev_a, job_a = await _seed(c, owner=OWNER_A)
            exp_b, rev_b, _job_b = await _seed(c, owner=OWNER_B)
            token = uuid.uuid4().hex
            await c.execute(
                "update jobs set status='running', lease_token=$2, lease_until=now()+interval '300 seconds' where id=$1",
                job_a, token,
            )
            with pytest.raises(Exception) as exc:
                await Publisher(c).publish(
                    job_id=job_a, lease_token=token, experiment_id=exp_b,
                    base_revision=rev_b, candidate_revision_id=revision_id_for(job_a, "f" * 64),
                    native_data=load_native("optics.convex_lens"), report_verdict="passed",
                )
            assert type(exc.value).__name__ == "OwnershipConflict", exc.value
            assert await c.fetchval("select count(*) from experiment_revisions") == 2
        finally:
            await c.close()

    asyncio.run(go())


def test_open_experiment_rejects_foreign_revision_and_search_is_scoped(uri, art_dir, engine_url):
    """§B.6：版本读取必须同时限定实验；检索面不得泄露别人的实例。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_a, rev_a, job_a = await _seed(c, owner=OWNER_A)
            # 同一 owner 的第二份实验：让「版本跨实验」这条守卫单独暴露出来，
            # 而不是被更早触发的归属检查顺手挡掉（那条也重要，另有断言）
            exp_a2, _rev_a2, _job_a2 = await _seed(c, owner=OWNER_A)
            exp_b, rev_b, _ = await _seed(c, owner=OWNER_B)
            job = JobContext(job_id=job_a, owner_id=OWNER_A, lease_token=uuid.uuid4().hex)
            service = ExperimentToolService(
                engine_client=EngineClient(engine_url), conn=c, artifact_dir=art_dir, job=job,
            )
            with pytest.raises(ConflictError):
                await service.open_experiment(OpenExperimentInput(
                    experiment_id=str(exp_a), revision_id=str(rev_b), template_id="optics.convex_lens"))
            # 拒绝之后不得留下任何工作态：静默回落到默认模板 = 把别人的场景换成干净的新场景
            assert await c.fetchval("select count(*) from experiment_candidates") == 0

            found = await service.search_experiments({"query": "", "limit": 50})
            ids = {it.experiment_id for it in found.items if it.experiment_id}
            assert str(exp_b) not in ids, ids
            assert str(rev_b) not in ids
        finally:
            await c.close()

    asyncio.run(go())


def test_two_workers_cannot_double_publish(uri, art_dir, engine_url):
    """重叠执行的第二个 Worker 只能被挡在门外：一份交付、一个版本。

    构造的是接管场景：A 没心跳、租约 1s，规划要 2s——A 跑到一半租约到期，B 领走并跑完。
    要求「不双发布」不是靠约定，而是发布事务里那句 `lease_token` 守卫在 SQL 上成立。
    """

    async def go():
        ca = await asyncpg.connect(uri)
        cb = await asyncpg.connect(uri)
        try:
            await _schema(ca)
            exp_id, rev_id, job_id = await _seed(ca)
            wa = make_worker(ca, engine_url=engine_url, artifact_dir=art_dir,
                             planner=SlowPlanner(_focal_proposal(), 2.0), lease_seconds=1)
            task_a = asyncio.create_task(wa.run_once())
            await asyncio.sleep(1.3)
            wb = make_worker(cb, engine_url=engine_url, artifact_dir=art_dir,
                             planner=SlowPlanner(_focal_proposal(), 2.0), lease_seconds=120)
            result_b = await wb.run_once()
            result_a = await task_a

            revisions = await ca.fetchval("select count(*) from experiment_revisions")
            assert int(revisions) == 2, f"出现了双发布：{revisions} 个版本；A={result_a} B={result_b}"
            head = await ca.fetchval("select head_revision_id from experiments where id=$1", exp_id)
            assert head is not None
            arts = await ca.fetchval(
                "select count(*) from artifacts where revision_id=$1 and storage_key like '%native.json'", head)
            assert int(arts) == 1, arts
            status = await ca.fetchval("select status from jobs where id=$1", job_id)
            assert status == "succeeded", (status, result_a, result_b)
            # 丢权的那个 Worker 必须可见地停下来，而不是静默地又发一版
            assert ("failed" in result_a and result_a["failed"] in ("LEASE_LOST", "CANDIDATE_VERSION_CONFLICT")) \
                or "stopped" in result_a, result_a
        finally:
            await ca.close()
            await cb.close()

    asyncio.run(go())


def _client_for(app, owner: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t",
        headers={"X-Owner-Id": owner},
    )


def test_cross_owner_api_access_is_refused(uri, art_dir):
    """§B.5：B 不能查、改、下载 A 的实验 / 任务 / 版本 / 产物。"""

    async def go():
        app = create_app(uri, art_dir)
        async with app.router.lifespan_context(app):
            async with _client_for(app, OWNER_A) as a, _client_for(app, OWNER_B) as b:
                exp = (await a.post("/api/v1/experiments", params={"template_id": "optics.convex_lens"})).json()
                job = (await a.post(
                    "/api/v1/jobs",
                    json={"experiment_id": exp["experiment_id"], "base_revision": exp["base_revision"],
                          "prompt": "把焦距改成 15cm"},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )).json()
                job_id = job["job_id"]

                # B 视角：一律 404，不给「存在但不可访问」的探针信号
                assert (await b.get(f"/api/v1/experiments/{exp['experiment_id']}")).status_code == 404
                assert (await b.get(f"/api/v1/jobs/{job_id}")).status_code == 404
                assert (await b.get(f"/api/v1/experiments/{exp['experiment_id']}/revisions")).json() == {"revisions": []}
                assert (await b.post(
                    f"/api/v1/jobs/{job_id}/cancel",
                )).status_code == 404
                assert (await b.post(
                    f"/api/v1/experiments/{exp['experiment_id']}/rollback",
                    json={"target_revision_id": exp["base_revision"]},
                )).status_code == 404
                # B 也不能把自己的任务挂到 A 的实验上
                bad = await b.post(
                    "/api/v1/jobs",
                    json={"experiment_id": exp["experiment_id"], "base_revision": exp["base_revision"],
                          "prompt": "别人的实验"},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                assert bad.status_code == 404, bad.text

                # A 自己看得见，证明不是把接口全打死
                assert (await a.get(f"/api/v1/experiments/{exp['experiment_id']}")).status_code == 200
                assert (await a.get(f"/api/v1/jobs/{job_id}")).status_code == 200

                # base_revision 不是当前 head：提交即拒，不等到 packaging 才撞乐观并发
                stale = await a.post(
                    "/api/v1/jobs",
                    json={"experiment_id": exp["experiment_id"], "base_revision": str(uuid.uuid4()),
                          "prompt": "过期版本"},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                assert stale.status_code == 409, stale.text
        return None

    asyncio.run(go())


def test_fixed_dev_identity_can_be_disabled(uri, art_dir, monkeypatch):
    """生产姿态：关掉开发身份之后，没有网关凭据就连不上任何资源。"""
    monkeypatch.setenv("EDUFORGE_GATEWAY_TOKEN", "s3cret-gateway-token")
    monkeypatch.delenv("EDUFORGE_ALLOW_DEV_IDENTITY", raising=False)

    async def go():
        app = create_app(uri, art_dir, allow_dev_identity=False)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as anon:
                r = await anon.get("/api/v1/experiments/00000000-0000-0000-0000-000000000000")
                assert r.status_code == 401, r.text
                assert r.json()["detail"]["code"] == "IDENTITY_REQUIRED"
                # 静态模板清单不泄露任何用户数据，允许免身份读取
                assert (await anon.get("/api/v1/templates")).status_code == 200
            headers = {"X-Owner-Id": "teacher-gw", "X-Gateway-Token": "s3cret-gateway-token"}
            async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=headers) as ok:
                assert (await ok.get("/api/v1/templates")).status_code == 200
                r = await ok.get("/api/v1/experiments/00000000-0000-0000-0000-000000000000")
                assert r.status_code == 404, r.text
            wrong = {"X-Owner-Id": "teacher-gw", "X-Gateway-Token": "nope"}
            async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=wrong) as bad:
                assert (await bad.get("/api/v1/templates/anything")).status_code in (200, 401, 404)
                r = await bad.get("/api/v1/experiments/00000000-0000-0000-0000-000000000000")
                assert r.status_code == 401, r.text

    asyncio.run(go())
