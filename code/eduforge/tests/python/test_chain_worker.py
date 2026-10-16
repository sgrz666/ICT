"""生产组合根的端到端链路（§2.2 调用栈 + §3.5 发布 + §6.1 使用链）。

API 提交 → 真实 Worker 跑完五阶段 → 原子发布 → 产物下载，每一步都走生产代码
（`worker.steps.Chain`、`api.create_app`），不是测试里另拼一套——否则测的是一条链、
Demo 跑的是另一条。

只有规划是注入的固定提案（本机没有模型 key）；这不构成规划能力的证据，
GATE-6 的模型对照仍然开放。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

import asyncpg
import httpx
import pgserver
import pytest

from eduforge.api.main import create_app
from eduforge.domain.contracts import EditProposal, SetParameter, SetView
from eduforge.infrastructure.db.repositories import JOBS_DDL
from eduforge.worker.main import SimulatedCrash
from eduforge.worker.steps import StaticPlanner, artifact_path, derived_id, make_worker, scene_bytes

TABLES = ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments")


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-chain-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture(scope="module")
def art_dir():
    return Path(tempfile.mkdtemp(prefix="eduforge-chain-art-"))


def focal_proposal(cm: float, entity: str = "lens_1") -> EditProposal:
    return EditProposal(
        route="config",
        operations=[SetParameter(entity_id=entity, parameter="focal_length_cm", value=cm)],
    )


def run_chain(uri, art_dir, engine_url, proposal, *, prompt="把凸透镜焦距改成新的值，看看像面搬到哪块屏"):
    """建实验 → 提交任务 → 真实 Worker 跑一遍 → 用业务 API 读回状态。"""

    async def outer():
        app = create_app(uri, art_dir)
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in TABLES:
                    await c.execute(f"delete from {t}")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ) as client:
                exp = (await client.post(
                    "/api/v1/experiments", params={"template_id": "optics.convex_lens"}
                )).json()
                job_id = uuid.UUID((await client.post(
                    "/api/v1/jobs",
                    json={"experiment_id": exp["experiment_id"],
                          "base_revision": exp["base_revision"], "prompt": prompt},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )).json()["job_id"])

                conn = await asyncpg.connect(uri)
                try:
                    worker = make_worker(
                        conn, engine_url=engine_url, artifact_dir=art_dir,
                        planner=StaticPlanner(proposal), lease_seconds=120,
                    )
                    worker_result = await worker.run_once()
                finally:
                    await conn.close()

                job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
                detail = (await client.get(f"/api/v1/experiments/{exp['experiment_id']}")).json()
                dl = await client.get(f"/api/v1/artifacts/{derived_id(job_id, 'artifact')}/download")
                listing = await client.get(f"/api/v1/revisions/{derived_id(job_id, 'revision')}/artifacts")
                rows = {}
                async with app.state.pool.acquire() as c:
                    rows["building"] = await c.fetchrow(
                        "select payload from job_events where job_id=$1 and stage='building' "
                        "and event_type='stage_done' order by sequence", job_id)
                    rows["rev_count"] = await c.fetchval(
                        "select count(*) from experiment_revisions where experiment_id=$1",
                        uuid.UUID(exp["experiment_id"]))
                    rows["art_count"] = await c.fetchval(
                        "select count(*) from artifacts where revision_id=$1",
                        derived_id(job_id, "revision"))
                return {
                    "exp": exp, "job_id": job_id, "job": job, "detail": detail,
                    "worker": worker_result, "download": dl, "rows": rows,
                    "listing": listing,
                }

    return asyncio.run(outer())


def test_chain_publishes_and_delivers_exactly_the_hashed_bytes(uri, art_dir, engine_url):
    out = run_chain(uri, art_dir, engine_url, focal_proposal(15))

    assert out["worker"]["last_stage"] == "packaging", out["worker"]
    assert out["job"]["status"] == "succeeded", out["job"]
    assert [e["stage"] for e in out["job"]["events"] if e["event_type"] == "stage_done"] == [
        "planning", "editing", "building", "validating", "packaging"
    ]

    cand = derived_id(out["job_id"], "revision")
    assert out["detail"]["head_revision"] == str(cand), "head 必须前进到本次候选版本"
    assert out["detail"]["revision_count"] == 2, out["detail"]
    assert out["rows"]["rev_count"] == 2
    assert out["rows"]["art_count"] == 1, "同一候选版本被登记了多份产物"

    assert out["download"].status_code == 200, out["download"].text
    body = out["download"].content
    assert hashlib.sha256(body).hexdigest() == out["download"].headers["x-content-sha256"]
    # 交付字节就是 building 算指纹那份
    building_payload = json.loads(out["rows"]["building"]["payload"])
    assert building_payload["sha256"] == out["download"].headers["x-content-sha256"]
    assert scene_bytes(json.loads(body)) == body, "落盘字节的写法必须与 scene_bytes 一致"
    assert (artifact_path(art_dir, cand)).read_bytes() == body

    scene = json.loads(body)
    lens = [o for o in scene["objs"] if o.get("name") == "lens_1"][0]
    assert lens["focalLength"] == 150, "15cm × units_per_unit 10 才是场景单位"
    assert scene["version"] == 5

    # 产物清单是前端唯一能拿来下载的入口；它给的 sha256 必须与实际交付字节一致
    listed = out["listing"].json()
    assert listed["revision_id"] == str(derived_id(out["job_id"], "revision"))
    assert len(listed["artifacts"]) == 1, listed
    assert listed["artifacts"][0]["sha256"] == out["download"].headers["x-content-sha256"]


def test_policy_rejection_is_terminal_and_touches_nothing(uri, art_dir, engine_url):
    """未登记的对象：策略层拒，任务可见地失败，而不是永远转圈。"""
    out = run_chain(uri, art_dir, engine_url, focal_proposal(15, entity="lens_9"))

    assert out["job"]["status"] == "failed", out["job"]
    assert out["job"]["error_code"] == "PARAMETER_NOT_REGISTERED"
    assert out["job"]["stage"] == "planning", out["job"]
    assert out["detail"]["revision_count"] == 1, "被拒的任务不得新增版本"
    assert out["detail"]["head_revision"] == out["exp"]["base_revision"]
    assert out["download"].status_code == 404
    assert not any(e["event_type"] == "stage_done" for e in out["job"]["events"]
                   if e["stage"] in ("editing", "building", "validating", "packaging"))


def test_validation_failure_blocks_publish(uri, art_dir, engine_url):
    """f=5、u=30 ⇒ 预测像距 6cm，落在屏阵列之外：实测光斑不成像。

    这条不是"为了让分支有覆盖而编的失败"，而是 GATE-4 实测过的物理事实：
    像面在阵列外时最清晰屏的 rms 远超阈值，独立参考据此拒绝发布。
    """
    out = run_chain(uri, art_dir, engine_url, focal_proposal(5))

    assert out["job"]["status"] == "failed", out["job"]
    assert out["job"]["error_code"] == "VALIDATION_NOT_PASSED"
    assert out["detail"]["head_revision"] == out["exp"]["base_revision"], "验证不过却前进了 head"
    assert out["detail"]["revision_count"] == 1
    assert out["download"].status_code == 404
    # building 已经落了文件（阶段顺序如此），但没有 revision 指向它——
    # 检查一遍别让它悄悄变成"孤儿产物也能下载"
    assert out["rows"]["rev_count"] == 1


def test_cli_run_once_processes_a_real_job(uri, art_dir, engine_url):
    """`python -m eduforge.worker.run --once` 这条命令行本身也要真跑过。

    上面几条用的是库函数；进程入口的 argparse、环境变量校验、横幅与退出码
    只有起真进程才算验证过——文档里"本机可以跑起来"那句话不能只靠推断。
    """
    import subprocess
    import sys

    exp_id, base_rev, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def seed():
        c = await asyncpg.connect(uri)
        try:
            await c.execute(JOBS_DDL)
            for t in TABLES:
                await c.execute(f"delete from {t}")
            native = json.loads((Path(__file__).resolve().parents[2] / "catalog" / "templates" /
                                 "optics" / "convex-lens" / "native.json").read_text(encoding="utf-8"))
            await c.execute(
                "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,'local-dev',$2,$3)",
                exp_id, "optics.convex_lens", base_rev,
            )
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics',$3::jsonb)",
                base_rev, exp_id, json.dumps(native),
            )
            await c.execute(
                """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                                     idempotency_key, request_hash)
                   values ($1,'local-dev',$2,$3,$4,'queued',$5,'h')""",
                job_id, exp_id, base_rev, "把焦距改成 15 厘米", uuid.uuid4(),
            )
        finally:
            await c.close()

    asyncio.run(seed())

    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    # 子进程横幅是中文，而 Windows 控制台默认 GBK：`text=True` 会按本地编码解码，
    # 一旦环境里有 PYTHONIOENCODING=utf-8 就会读到 None 并抛 UnicodeDecodeError。
    # 两侧都钉死 UTF-8，用例才不依赖调用它的 shell 配置。
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "eduforge.worker.run", "--once",
         "--planner-static-focal", "15",
         "--dsn", uri, "--engine-url", engine_url, "--artifact-dir", str(art_dir)],
        capture_output=True, text=True, encoding="utf-8", timeout=180, env=env,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    # 子进程 stderr 走控制台编码，中文断言留给库层用例；这里按 ASCII 标记查横幅
    assert "--planner-static-focal" in proc.stderr, proc.stderr

    reported = json.loads(proc.stdout.strip().splitlines()[-1])
    assert reported["last_stage"] == "packaging", reported

    async def check():
        c = await asyncpg.connect(uri)
        try:
            return (await c.fetchval("select status from jobs where id=$1", job_id),
                    await c.fetchval("select head_revision_id from experiments where id=$1", exp_id))
        finally:
            await c.close()

    status, head = asyncio.run(check())
    assert status == "succeeded"
    assert str(head) == str(derived_id(job_id, "revision"))


def test_recovery_rebuilds_context_from_persisted_facts(uri, art_dir, engine_url):
    """崩在 packaging 之前，接管者没有内存缓存：候选字节与 verdict 都要从库里重建。

    同时钉住派生 id：重跑必须落在同一个候选版本上，不能插出第二个。
    """
    proposal = focal_proposal(15)
    exp_id = None

    async def outer():
        nonlocal exp_id
        app = create_app(uri, art_dir)
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in TABLES:
                    await c.execute(f"delete from {t}")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ) as client:
                exp = (await client.post(
                    "/api/v1/experiments", params={"template_id": "optics.convex_lens"}
                )).json()
                exp_id = exp["experiment_id"]
                job_id = uuid.UUID((await client.post(
                    "/api/v1/jobs",
                    json={"experiment_id": exp["experiment_id"],
                          "base_revision": exp["base_revision"], "prompt": "焦距改 15 厘米"},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )).json()["job_id"])

                a = await asyncpg.connect(uri)
                worker_a = make_worker(a, engine_url=engine_url, artifact_dir=art_dir,
                                       planner=StaticPlanner(proposal), lease_seconds=1)
                with pytest.raises(SimulatedCrash):
                    await worker_a.run_once(crash_before="packaging")
                await a.close()

                # 等租约过期，第二个 worker 才有资格接管
                time.sleep(1.5)
                b = await asyncpg.connect(uri)
                worker_b = make_worker(b, engine_url=engine_url, artifact_dir=art_dir,
                                       planner=StaticPlanner(proposal), lease_seconds=120)
                result_b = await worker_b.run_once()
                await b.close()

                job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
                detail = (await client.get(f"/api/v1/experiments/{exp_id}")).json()
                dl = await client.get(f"/api/v1/artifacts/{derived_id(job_id, 'artifact')}/download")
                async with app.state.pool.acquire() as c:
                    rev_count = await c.fetchval(
                        "select count(*) from experiment_revisions where experiment_id=$1",
                        uuid.UUID(exp_id))
                    art_count = await c.fetchval(
                        "select count(*) from artifacts where revision_id=$1",
                        derived_id(job_id, "revision"))
                    starts = await c.fetch(
                        "select stage, event_type, count(*) n from job_events where job_id=$1 "
                        "group by stage, event_type order by stage, event_type", job_id)
                return {
                    "job_id": job_id, "job": job, "detail": detail, "dl": dl,
                    "result_b": result_b, "rev_count": rev_count, "art_count": art_count,
                    "starts": {f"{r['stage']}/{r['event_type']}": r["n"] for r in starts},
                }

    out = asyncio.run(outer())

    assert out["result_b"]["last_stage"] == "packaging"
    assert out["job"]["status"] == "succeeded", out["job"]
    assert out["detail"]["revision_count"] == 2
    assert out["rev_count"] == 2, "派生 id 失效，恢复时插出了多余版本"
    assert out["art_count"] == 1, "同一候选被登记成多份产物"
    assert out["dl"].status_code == 200
    # planning/editing/building/validating 各只启动一次（已完成的阶段被跳过），
    # packaging 因崩溃重跑：started 两次、done 一次
    assert out["starts"]["planning/stage_start"] == 1
    assert out["starts"]["building/stage_start"] == 1
    assert out["starts"]["packaging/stage_start"] == 2
    assert out["starts"]["packaging/stage_done"] == 1


def test_chain_composite_operations_publish(uri, art_dir, engine_url):
    """验证复合教学需求：修改焦距到 15cm 并显示测量记录表（SetParameter + SetView）。
    Worker 支持复合操作且门禁核验通过，正常完成 5 阶段并发布新版本。
    """
    composite = EditProposal(
        route="config",
        operations=[
            SetParameter(entity_id="lens_1", parameter="focal_length_cm", value=15),
            SetView(view_id="measurement_table", visible=True),
        ],
    )
    out = run_chain(uri, art_dir, engine_url, composite, prompt="把凸透镜焦距改成 15cm，并显示测量记录表")
    assert out["worker"]["last_stage"] == "packaging", out["worker"]
    assert out["job"]["status"] == "succeeded", out["job"]
    assert out["detail"]["revision_count"] == 2


def test_chain_focal_parallel_beams_at_infinity(uri, art_dir, engine_url):
    """f=30cm 时物距 u=30cm 等于焦距，折射光线为平行光束（像在无穷远）。
    门禁物理规则判定通过（focal_parallel_beams: passed），不再因 NoneType 异常报错。
    """
    out = run_chain(uri, art_dir, engine_url, focal_proposal(30), prompt="把焦距改成 30cm，物点正好在焦点上")
    assert out["worker"]["last_stage"] == "packaging", out["worker"]
    assert out["job"]["status"] == "succeeded", out["job"]
    assert out["detail"]["revision_count"] == 2


def test_chain_virtual_image_valid(uri, art_dir, engine_url):
    """f=40cm 时物距 u=30cm 小于焦距，成正立放大虚像。
    门禁物理规则判定通过（virtual_image_valid: passed），不再误要求实像屏聚焦。
    """
    out = run_chain(uri, art_dir, engine_url, focal_proposal(40), prompt="把焦距改成 40cm，成放大虚像")
    assert out["worker"]["last_stage"] == "packaging", out["worker"]
    assert out["job"]["status"] == "succeeded", out["job"]
    assert out["detail"]["revision_count"] == 2


def test_chain_multiple_parameter_edits_validating(uri, art_dir, engine_url):
    """验证批量参数编辑（focal_length_cm + object_distance_cm）由 Worker 成功应用与闭环门禁核验。
    物距从候选场景正确提取（u=20cm），预测像距 v=30cm 且与实测屏一致，门禁全部核验通过。
    """
    multi = EditProposal(
        route="config",
        operations=[
            SetParameter(entity_id="lens_1", parameter="focal_length_cm", value=12),
            SetParameter(entity_id="object_1", parameter="object_distance_cm", value=20),
            SetView(view_id="measurement_table", visible=True),
        ],
    )
    out = run_chain(uri, art_dir, engine_url, multi, prompt="焦距改为12cm，物距设为20cm，显示测量表")
    assert out["worker"]["last_stage"] == "packaging", out["worker"]
    assert out["job"]["status"] == "succeeded", out["job"]
    assert out["detail"]["revision_count"] == 2


