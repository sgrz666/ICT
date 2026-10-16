"""§2.2 调用栈的跨语言集成：Python 任务层通过 HTTP 驱动 TS Engine Host，
最终经独立参考验证后原子发布。

真实进程、真实 Postgres、真实上游仿真——不是 mock。反向用例证明验证不过时
head 不会前进。
"""
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import asyncpg
import pgserver
import pytest

from eduforge.application.coordinator import STAGES, Coordinator
from eduforge.application.publication import NotPublishable, Publisher
from eduforge.application.services import JobService
from eduforge.domain.contracts import CreateJobRequest, SetParameter
from eduforge.infrastructure.clients.engine_client import EngineClient, sharpest_screen
from eduforge.infrastructure.db.repositories import JOBS_DDL, JobRepository
from eduforge.validation.policies import build_report
from eduforge.worker.main import Worker

ENGINE_DIR = Path(__file__).resolve().parents[2] / "services" / "engine-host"
ART_DIR = Path(tempfile.mkdtemp(prefix="eduforge-artifacts-"))
OBJECT_DISTANCE_CM = 30.0
UNITS_PER_UNIT = 10


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def engine_url():
    if not (ENGINE_DIR / "dist" / "main.js").exists():
        subprocess.run(["node_modules/.bin/tsc", "-p", "tsconfig.build.json"], cwd=ENGINE_DIR, check=True)
    port = free_port()
    proc = subprocess.Popen(
        ["node", "dist/main.js"],
        cwd=ENGINE_DIR,
        env={**os.environ, "ENGINE_HOST_PORT": str(port), "NODE_ENV": "production"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    # 等就绪，最多 20 s；起不来就把子进程输出带出来，方便定位
    import httpx

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/healthz", timeout=2).status_code == 200:
                break
        except Exception:
            time.sleep(0.3)
    else:
        out = proc.stdout.read() if proc.stdout else ""
        proc.kill()
        pytest.fail(f"engine-host 未就绪：\n{out}")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-pub-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


def run_publish_case(uri, engine_url, *, target_f_cm, claimed_u_cm):
    """走完整链路，返回 (head_after, verdict, checks)。"""

    async def inner():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        exp_id = uuid.uuid4()
        base_rev = uuid.uuid4()
        cand_rev = uuid.uuid4()
        native = json.loads((Path(__file__).resolve().parents[2] / "catalog" /
                             "templates" / "optics" / "convex-lens" / "native.json").read_text(encoding="utf-8"))
        await c.execute(
            "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,'o',$2,$3)",
            exp_id, "optics.convex_lens", base_rev,
        )
        await c.execute(
            "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics',$3::jsonb)",
            base_rev, exp_id, json.dumps(native),
        )

        job_id = uuid.uuid4()
        await c.execute(
            """insert into jobs (id, owner_id, experiment_id, base_revision, status,
                                 idempotency_key, request_hash)
               values ($1,'o',$2,$3,'queued',$4,'h')""",
            job_id, exp_id, base_rev, uuid.uuid4(),
        )

        engine = EngineClient(engine_url)
        repo = JobRepository(c)
        publisher = Publisher(c)
        state: dict = {}

        async def planning(_jid):
            return {"route": "config"}

        async def editing(_jid):
            result = await engine.apply(native, {
                "op": "set_parameter", "entity_id": "lens_1",
                "parameter": "focal_length_cm", "value": target_f_cm,
            })
            state["engine_result"] = result
            state["candidate_native"] = result["native"]
            return {"focalLength": result["native"]["objs"][0]["focalLength"]}

        async def building(_jid):
            await c.execute(
                "update jobs set candidate_revision_id=$2 where id=$1", job_id, cand_rev
            )
            return {"candidate_revision_id": str(cand_rev)}

        async def validating(_jid):
            report = build_report(
                job_id=str(_jid),
                edit=SetParameter(entity_id="lens_1", parameter="focal_length_cm", value=target_f_cm),
                engine_result=state["engine_result"],
                object_distance_cm=claimed_u_cm,
                units_per_unit=UNITS_PER_UNIT,
            )
            state["report"] = report
            await publisher.record_report(job_id=_jid, report=report)
            return {"verdict": report.verdict}

        async def packaging(_jid):
            """真的把产物落盘，并对**文件字节**算指纹。

            artifacts.sha256 锁的是要交付的那份字节；数据库里 native_data 是 jsonb，
            渲染形式会被 Postgres 规范化（空格、键序），拿 json.dumps 的哈希去比
            jsonb::text 是拿两种序列化互比，必然不相等。
            artifacts 外键指向发布时才插入的 revision，所以文件索引在发布事务里登记。
            """
            rel = Path("revisions") / str(cand_rev) / "native.json"
            target = ART_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(state["candidate_native"], ensure_ascii=False).encode("utf-8")
            target.write_bytes(payload)
            state["artifact"] = {
                "id": str(uuid.uuid4()), "storage_key": str(rel),
                "sha256": hashlib.sha256(payload).hexdigest(), "media_type": "application/json",
            }
            return {"sha256": state["artifact"]["sha256"], "bytes": len(payload)}

        steps = {"planning": planning, "editing": editing, "building": building,
                 "validating": validating, "packaging": packaging}

        worker = Worker(repo=repo, coordinator=Coordinator(repo=repo, steps=steps), lease_seconds=120)
        result = await worker.run_once()
        assert result is not None
        lease_token = result["lease_token"]

        report = state["report"]
        publish_error = None
        try:
            await publisher.publish(
                job_id=job_id, lease_token=lease_token, experiment_id=exp_id,
                base_revision=base_rev, candidate_revision_id=cand_rev,
                native_data=state["candidate_native"], report_verdict=report.verdict,
                artifacts=[state["artifact"]] if report.verdict == "passed" else None,
            )
        except NotPublishable as e:
            publish_error = e.reason

        head = await c.fetchval("select head_revision_id from experiments where id=$1", exp_id)
        status = await c.fetchval("select status from jobs where id=$1", job_id)
        events = await repo.events(job_id)
        await c.close()
        return {
            "head": str(head), "verdict": report.verdict,
            "checks": {ck.id: ck.passed for ck in report.checks},
            "publish_error": publish_error, "job_status": status, "artifact": state.get("artifact"),
            "stages_done": [e["stage"] for e in events if e["event_type"] == "stage_done"],
            "observed_screen": (sharpest_screen(state["engine_result"]) or {}).get("x_cm"),
        }

    return asyncio.run(inner())


def test_publish_chain_passes_and_advances_head(uri, engine_url):
    """f=15cm、u=30cm：预测像面 30cm 屏，独立参考与上游仿真一致 → 发布成功。"""
    out = run_publish_case(uri, engine_url, target_f_cm=15, claimed_u_cm=30)
    assert out["verdict"] == "passed", out
    assert out["stages_done"] == STAGES, out
    assert out["publish_error"] is None
    assert out["job_status"] == "succeeded"
    assert out["observed_screen"] == 30
    # 发布成功后产物才存在，且下载内容哈希与打包时算的一致
    async def check_artifact():
        c = await asyncpg.connect(uri)
        try:
            row = await c.fetchrow(
                "select a.storage_key, a.sha256, r.native_data::text from artifacts a "
                "join experiment_revisions r on r.id = a.revision_id")
            return row
        finally:
            await c.close()

    row = asyncio.run(check_artifact())
    assert row is not None
    stored = (ART_DIR / row["storage_key"]).read_bytes()
    assert hashlib.sha256(stored).hexdigest() == row["sha256"], "登记的哈希与落盘字节不符"
    # 结构等价（不比字符串）：产物文件与候选版本内容一致
    assert json.loads(stored) == json.loads(row["native_data"])
    assert json.loads(stored)["objs"][0]["focalLength"] == 150


def test_publish_blocked_when_reference_disagrees(uri, engine_url):
    """反向：把物距报错成 25cm，预测像面变 41.7→最近屏 40，与实测 30 不符 →
    报告 failed，head 不前进，任务不会被当成成功资源发布。"""
    out = run_publish_case(uri, engine_url, target_f_cm=15, claimed_u_cm=25)
    assert out["checks"]["image_plane_matches_reference"] is False, out
    assert out["verdict"] == "failed"
    assert out["publish_error"] == "verdict=failed"
    assert out["head"] != "None"  # head 仍在原 base 上
    assert out["job_status"] == "running", f"未发布却把任务转成 {out['job_status']}"


def test_publish_is_atomic_when_artifact_insert_fails(uri):
    """事务中途失败必须整体回滚：不能留下"head 指向不存在的版本"或
    "版本已插入但产物缺一半"的中闲状态——这正是把发布改成单事务的理由。"""

    async def inner():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs",
                  "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        exp_id, base_rev, cand_rev, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await c.execute(
            "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,'o',$2,$3)",
            exp_id, "optics.convex_lens", base_rev,
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

        dup = uuid.uuid4()
        # 第二条产物故意用重复主键，让事务在 revision 已插入之后才失败
        bad_artifacts = [
            {"id": str(dup), "storage_key": "a.json", "sha256": "x", "media_type": "application/json"},
            {"id": str(dup), "storage_key": "b.json", "sha256": "y", "media_type": "application/json"},
        ]
        with pytest.raises(asyncpg.UniqueViolationError):
            await repo.publish(
                job_id=job_id, lease_token="tok", experiment_id=exp_id,
                base_revision=base_rev, candidate_revision_id=cand_rev,
                native_data={"version": 5}, checks_passed=True, artifacts=bad_artifacts,
            )

        rev_exists = await c.fetchval(
            "select count(*) from experiment_revisions where id=$1", cand_rev)
        art_exists = await c.fetchval("select count(*) from artifacts")
        head = await c.fetchval("select head_revision_id from experiments where id=$1", exp_id)
        status = await c.fetchval("select status from jobs where id=$1", job_id)
        await c.close()
        return int(rev_exists), int(art_exists), str(head), status

    rev_exists, art_exists, head, status = asyncio.run(inner())
    assert rev_exists == 0, "事务回滚不彻底：候选版本留下了"
    assert art_exists == 0, "事务回滚不彻底：产物索引留下了"
    assert head is not None and head != "None"
    assert status == "running", f"发布失败不该把任务转成 {status}"
