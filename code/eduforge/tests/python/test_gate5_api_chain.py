"""§6.1 最小完整使用链：选模板 → 建实验 → 提交任务 → 查任务 → 下载产物。

真实 PostgreSQL + 真实 asyncpg 连接池 + ASGI 内存传输，不起子进程。
断言的是链路可走通与幂等语义，不是"路由注册上了"。
"""
import asyncio
import hashlib
import json
import tempfile
import uuid
from pathlib import Path

import asyncpg
import httpx
import pgserver
import pytest

from eduforge.api.main import LOCAL_DEV_OWNER, create_app
from eduforge.infrastructure.catalog import CATALOG
from eduforge.infrastructure.db.migrations import apply_migrations

ART_INSERT = (
    "insert into artifacts (id, revision_id, storage_key, sha256, media_type) "
    "values ($1,$2,$3,$4,'application/json')"
)


def _control_numbers(manifest_text: str) -> dict:
    """从清单原文取 controls 段里第一个控件的 min/max/initial。

    故意不复用 catalog 的解析器：拿同一份代码去验同一份代码得到的数，
    什么也证明不了。这里直接从文件文本读，才能发现 API 与清单漂移。
    """
    out: dict[str, float] = {}
    inside = False
    for line in manifest_text.splitlines():
        stripped = line.strip()
        if not inside:
            inside = stripped == "controls:"
            continue
        if inside and not line.startswith((" ", "-")) and stripped.endswith(":"):
            break
        for key in ("min", "max", "initial"):
            if stripped.startswith(f"{key}:") and key not in out:
                out[key] = float(stripped.split(":", 1)[1].strip())
    assert set(out) == {"min", "max", "initial"}, f"清单里读不到量程三件套：{out}"
    return out


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-api-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture(scope="module")
def art_dir():
    return Path(tempfile.mkdtemp(prefix="eduforge-art-"))


def run_in_app(uri, art_dir, test_body):
    """显式进入 app 的 lifespan（ASGITransport 不会自己跑 startup），再发请求。"""

    async def outer():
        app = create_app(uri, art_dir)
        async with app.router.lifespan_context(app):
            # 每个用例从干净数据开始
            async with app.state.pool.acquire() as c:
                for t in ("artifacts", "job_events", "jobs", "experiment_revisions", "experiments"):
                    await c.execute(f"delete from {t}")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await test_body(client, app.state.pool, art_dir)

    asyncio.run(outer())


def test_full_chain(uri, art_dir):
    async def body(client, pool, art_dir):
        # 1) 模板目录
        r = await client.get("/api/v1/templates")
        assert r.status_code == 200
        ids = [t["template_id"] for t in r.json()["templates"]]
        assert "optics.convex_lens" in ids
        assert "mechanics.pendulum" not in ids  # 首批只做光学，别把没接的当成接了

        # 量程只能有清单一个出处：API 报出来的 min/max/initial 必须就是 manifest 里那几个数
        tpl = [t for t in r.json()["templates"] if t["template_id"] == "optics.convex_lens"][0]
        lens = [c for c in tpl["controls"] if c["entity_id"] == "lens_1"]
        assert len(lens) == 1, tpl
        declared = _control_numbers(
            (CATALOG / "templates" / "optics" / "convex-lens" / "manifest.yaml").read_text(encoding="utf-8")
        )
        for field in ("min", "max", "initial"):
            assert lens[0][field] == declared[field], (
                f"{field}：API {lens[0][field]} 与清单 {declared[field]} 不一致"
            )
        assert lens[0]["label"] and lens[0]["unit"], "前端要靠 label/unit 生成控件，空值等于没暴露"
        assert tpl["units_per_unit"] == 10
        assert "config" in tpl["routes"] and "measurement_table" in tpl["views"]

        # 2) 建实验，拿到 base_revision
        r = await client.post("/api/v1/experiments", params={"template_id": "optics.convex_lens"})
        assert r.status_code == 201, r.text
        exp = r.json()
        assert exp["experiment_id"] and exp["base_revision"]

        # 未知模板
        assert (
            await client.post("/api/v1/experiments", params={"template_id": "no.such"})
        ).status_code == 404

        # 3) 提交任务
        key = str(uuid.uuid4())
        req = {
            "experiment_id": exp["experiment_id"],
            "base_revision": exp["base_revision"],
            "prompt": "把焦距改成 15 厘米，显示测量记录表",
        }
        r1 = await client.post("/api/v1/jobs", json=req, headers={"Idempotency-Key": key})
        assert r1.status_code == 202, r1.text
        job_id = r1.json()["job_id"]

        # 控制组：同键同体 → 同一个 job，不产生第二条
        r2 = await client.post("/api/v1/jobs", json=req, headers={"Idempotency-Key": key})
        assert r2.status_code == 202
        assert r2.json()["job_id"] == job_id

        # 同键不同体 → 409，且不覆盖原任务
        r3 = await client.post(
            "/api/v1/jobs", json={**req, "prompt": "改成 30 厘米"}, headers={"Idempotency-Key": key}
        )
        assert r3.status_code == 409
        assert r3.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"

        # 缺 Idempotency-Key 头 → 4xx，不允许无键提交
        assert (await client.post("/api/v1/jobs", json=req)).status_code == 422

        # 4) 查任务：queued、事件为空（还没被 Worker 领取）
        r = await client.get(f"/api/v1/jobs/{job_id}")
        assert r.status_code == 200
        got = r.json()
        assert got["status"] == "queued"
        assert got["events"] == []

        async with pool.acquire() as c:
            count = await c.fetchval("select count(*) from jobs")
        assert count == 1, f"幂等重放产生了多余任务：{count}"

        assert (await client.get(f"/api/v1/jobs/{uuid.uuid4()}")).status_code == 404

        # 5) 版本历史
        r = await client.get(f"/api/v1/experiments/{exp['experiment_id']}/revisions")
        assert r.status_code == 200
        assert len(r.json()["revisions"]) == 1

        # 6) 登记产物再下载：下载必须交付"登记哈希锁定的那份字节"
        async with pool.acquire() as c:
            native_text = await c.fetchval(
                "select native_data::text from experiment_revisions where id=$1",
                uuid.UUID(exp["base_revision"]),
            )
        payload = (json.dumps(json.loads(native_text), ensure_ascii=False) + "\n").encode("utf-8")
        rel = Path("revisions") / exp["base_revision"] / "native.json"
        target = art_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        art_id = uuid.uuid4()
        async with pool.acquire() as c:
            await c.execute(ART_INSERT, art_id, uuid.UUID(exp["base_revision"]), str(rel), digest)

        r = await client.get(f"/api/v1/artifacts/{art_id}/download")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/json")
        assert r.headers["x-content-sha256"] == digest
        # 字节级一致。只断言"头等于库里那个 sha256"是假校验：
        # 库里 native_data 是 jsonb，渲染形式和打包时算哈希的字节必然不同。
        assert r.content == payload
        scene = json.loads(r.content)
        assert scene["objs"][0]["name"] == "lens_1"
        assert len([o for o in scene["objs"] if o["type"] == "Detector"]) == 7

        assert (await client.get(f"/api/v1/artifacts/{uuid.uuid4()}/download")).status_code == 404

        # 文件不见了宁可 404，也不能退回 jsonb 文本充数
        target.unlink()
        r = await client.get(f"/api/v1/artifacts/{art_id}/download")
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "ARTIFACT_FILE_MISSING"

    run_in_app(uri, art_dir, body)


def test_download_refuses_hash_mismatch_and_traversal(uri, art_dir):
    """两条闸门都要有控制组：正常件必须成功，否则"被拦住"可能只是路由坏了。"""
    art_ok, art_bad, art_escape = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def body(client, pool, art_dir):
        exp_id, rev_id = uuid.uuid4(), uuid.uuid4()
        async with pool.acquire() as c:
            await c.execute(
                "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,$2,'optics.convex_lens',$3)",
                exp_id, LOCAL_DEV_OWNER, rev_id,
            )
            await c.execute(
                "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics','{}')",
                rev_id, exp_id,
            )
            good = b'{"objs": [],"dataVersion":5}'
            rel = Path("revisions") / str(rev_id) / "native.json"
            target = art_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(good)
            outside = art_dir.parent / f"outside-{uuid.uuid4().hex}.json"
            outside.write_bytes(b'{"secret": "must-not-leak"}')
            await c.execute(ART_INSERT, art_ok, rev_id, str(rel), hashlib.sha256(good).hexdigest())
            await c.execute(ART_INSERT, art_bad, rev_id, str(rel), "0" * 64)
            await c.execute(
                ART_INSERT, art_escape, rev_id, f"../{outside.name}",
                hashlib.sha256(outside.read_bytes()).hexdigest(),
            )

        r = await client.get(f"/api/v1/artifacts/{art_ok}/download")
        assert r.status_code == 200, f"控制组失败：{r.text}"
        assert r.content == good

        r = await client.get(f"/api/v1/artifacts/{art_bad}/download")
        assert r.status_code == 500, r.text
        assert r.json()["detail"]["code"] == "CONTENT_HASH_MISMATCH"

        r = await client.get(f"/api/v1/artifacts/{art_escape}/download")
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "STORAGE_KEY_OUT_OF_ROOT"
        assert "must-not-leak" not in r.text

    run_in_app(uri, art_dir, body)
