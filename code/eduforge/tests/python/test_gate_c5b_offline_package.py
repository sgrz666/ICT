"""Gate C §C.5b (R2)：用户真正下载完整离线实验包端到端闭环与负向测试。

涵盖：
1. 完整生产链发布后，通过 HTTP API 下载确定性 ZIP 离线实验包；
2. 校验 HTTP 响应头（x-content-sha256、accept-ranges、content-length、content-type）；
3. 支持 HTTP Range 范围请求（206 Partial Content / 416 Range Not Satisfiable）；
4. 解压至独立临时目录，逐文件校验 manifest 清单与整包摘要；
5. 使用独立 Chromium 打开解压后的静态包，实测光路渲染（canvasLight 像素 > 0，零脚本错误）；
6. 负向测试：篡改 ZIP（500）、缺失文件（404）、未授权跨用户下载（404）均被正确拦截。
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import http.server
import json
import socket
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pgserver
from playwright.sync_api import sync_playwright
import pytest

from eduforge.api.main import LOCAL_DEV_OWNER, create_app
from eduforge.application.candidate_service import native_bytes
from eduforge.application.package_builder import (
    MANIFEST_NAME,
    file_sha256,
    package_digest,
    verify_offline_zip,
    verify_package_on_disk,
)
from eduforge.domain.contracts import EditProposal, SetParameter
from eduforge.infrastructure.db.migrations import apply_migrations
from eduforge.infrastructure.db.repositories import artifact_id_for
from eduforge.worker.steps import make_worker

LIT_PIXELS = """() => {
  const c = document.getElementById("canvasLight");
  if (!c) return -1;
  let g = null;
  try { g = c.getContext("2d", { willReadFrequently: true }); } catch (e) { g = null; }
  if (!g) return -1;
  const d = g.getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i] > 12 || d[i+1] > 12 || d[i+2] > 12) n++;
  return n;
}"""

TABLES = (
    "artifacts", "validation_reports", "job_events", "jobs",
    "experiment_candidates", "experiment_revisions", "experiments",
)


class StaticPlanner:
    def __init__(self, proposal: EditProposal) -> None:
        self.proposal = proposal

    async def plan(self, _req) -> EditProposal:
        return self.proposal


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def pg_uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-c5b-pg-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture(scope="module")
def art_dir():
    return Path(tempfile.mkdtemp(prefix="eduforge-c5b-art-"))


async def _publish_offline_experiment(
    client: httpx.AsyncClient, uri: str, art_dir: Path, engine_url: str
) -> dict[str, Any]:
    """跑一次完整生产链，发布并返回包含 offline_package.zip 的修订上下文。"""
    proposal = EditProposal(
        route="config",
        operations=[SetParameter(entity_id="lens_1", parameter="focal_length_cm", value=15)],
    )

    exp = (await client.post(
        "/api/v1/experiments", params={"template_id": "optics.convex_lens"}
    )).json()
    job_id = uuid.UUID((await client.post(
        "/api/v1/jobs",
        json={"experiment_id": exp["experiment_id"],
              "base_revision": exp["base_revision"], "prompt": "焦距改为15cm生成离线包"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )).json()["job_id"])

    conn = await asyncpg.connect(uri)
    try:
        worker = make_worker(
            conn, engine_url=engine_url, artifact_dir=art_dir,
            planner=StaticPlanner(proposal), lease_seconds=120,
        )
        worker_res = await worker.run_once()
    finally:
        await conn.close()

    assert worker_res["last_stage"] == "packaging"
    job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert job["status"] == "succeeded"

    cand_rev = job["candidate_revision_id"]
    artifacts_resp = (await client.get(f"/api/v1/revisions/{cand_rev}/artifacts")).json()
    artifacts = artifacts_resp["artifacts"]
    zip_arts = [a for a in artifacts if a["media_type"] == "application/zip"]
    assert len(zip_arts) == 1, f"未登记 offline_zip 产物：{artifacts}"
    zip_art = zip_arts[0]

    return {
        "exp": exp,
        "job_id": job_id,
        "cand_rev": cand_rev,
        "artifacts": artifacts,
        "zip_id": zip_art["artifact_id"],
        "expected_sha": zip_art["sha256"],
    }


def test_e2e_publish_downloads_deterministic_zip_and_chromium_renders(pg_uri, art_dir, engine_url):
    """Gate C §C.5b R2 核心闭环：发布后下载 ZIP -> 解压独立目录 -> 逐文件核对 -> Chromium 真机离线跑通。"""
    async def dl():
        app = create_app(pg_uri, art_dir)
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in TABLES:
                    await c.execute(f"delete from {t}")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ) as client:
                ctx = await _publish_offline_experiment(client, pg_uri, art_dir, engine_url)
                zip_id = ctx["zip_id"]
                expected_sha = ctx["expected_sha"]

                resp = await client.get(f"/api/v1/artifacts/{zip_id}/download")
                assert resp.status_code == 200, resp.text
                assert resp.headers["content-type"] == "application/zip"
                assert resp.headers["accept-ranges"] == "bytes"
                assert resp.headers["x-content-sha256"] == expected_sha
                assert int(resp.headers["content-length"]) == len(resp.content)
                assert resp.headers["content-disposition"] == 'attachment; filename="offline_package.zip"'
                assert hashlib.sha256(resp.content).hexdigest() == expected_sha
                return ctx, resp.content

    ctx, zip_content = asyncio.run(dl())
    expected_sha = ctx["expected_sha"]

    # 3. 解压至全新独立临时目录
    extract_dir = Path(tempfile.mkdtemp(prefix="eduforge-c5b-extract-"))
    zip_temp = extract_dir / "downloaded.zip"
    zip_temp.write_bytes(zip_content)

    # 4. 验证 ZIP 完整性与安全
    zip_check = verify_offline_zip(zip_temp, expected_sha)
    assert zip_check["ok"] is True, zip_check
    assert zip_check["reason"] == "zip_matches_manifest"

    with zipfile.ZipFile(zip_temp, "r") as zf:
        zf.extractall(extract_dir)

    # 5. 逐文件比对 manifest 清单
    manifest_file = extract_dir / MANIFEST_NAME
    assert manifest_file.is_file(), "解压目录中缺少 manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["entry"] == "www/index.html"
    assert manifest["requires_local_static_server"] is True
    assert (extract_dir / "README.md").is_file(), "缺少离线说明 README.md"
    assert (extract_dir / "LICENSE").is_file(), "缺少许可文件 LICENSE"

    for entry in manifest["files"]:
        p = extract_dir / entry["path"]
        assert p.is_file(), f"清单中声明的文件未解压出来：{entry['path']}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == entry["sha256"]

    # 整包摘要验证
    recomputed_pkg_sha = package_digest(manifest["files"])
    assert recomputed_pkg_sha == manifest["package_sha256"]

    # 6. 使用独立本地 HTTP 服务与独立 Chromium 验证离线包真实光路渲染
    server_port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(extract_dir))
    httpd = http.server.HTTPServer(("127.0.0.1", server_port), handler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            # 打开解压后的静态离线包入口
            page.goto(f"http://127.0.0.1:{server_port}/www/index.html", wait_until="load")
            page.wait_for_selector("#sim", timeout=20000)

            deadline = time.time() + 30
            sim = None
            while time.time() < deadline:
                matches = [f for f in page.frames if "/simulator/" in (f.url or "")]
                if matches:
                    sim = matches[0]
                    break
                page.wait_for_timeout(200)
            assert sim is not None, f"离线包 index.html 中未加载模拟器 iframe，当前 frames: {page.frames}"

            sim.wait_for_selector("#canvasLight", timeout=25000)
            sim.wait_for_function(f"({LIT_PIXELS})() > 0", timeout=25000)
            lit_pixels = sim.evaluate(LIT_PIXELS)
            assert lit_pixels > 0, f"解压后的静态包光路未渲染（lit_pixels={lit_pixels}）"

            # 欢迎页面已被场景隐藏
            welcome = sim.locator("#welcome")
            if welcome.count() > 0:
                assert not welcome.is_visible(), "场景已载入但欢迎层未隐藏"

            browser.close()
            assert not page_errors, f"离线包运行存在脚本错误：{page_errors}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_download_range_requests(pg_uri, art_dir, engine_url):
    """支持 RFC 7233 Range 分段传输，避免大文件一次性爆内存。"""
    async def run():
        app = create_app(pg_uri, art_dir)
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in TABLES:
                    await c.execute(f"delete from {t}")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ) as client:
                ctx = await _publish_offline_experiment(client, pg_uri, art_dir, engine_url)
                zip_id = ctx["zip_id"]

                # 1. 先拿完整文件
                full = await client.get(f"/api/v1/artifacts/{zip_id}/download")
                assert full.status_code == 200
                total_size = len(full.content)

                # 2. 分段请求前 16 字节
                part1 = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"Range": "bytes=0-15"},
                )
                assert part1.status_code == 206
                assert part1.headers["content-range"] == f"bytes 0-15/{total_size}"
                assert part1.headers["content-length"] == "16"
                assert part1.content == full.content[:16]

                # 3. 后缀范围请求最后 32 字节
                part2 = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"Range": "bytes=-32"},
                )
                assert part2.status_code == 206
                assert part2.headers["content-range"] == f"bytes {total_size - 32}-{total_size - 1}/{total_size}"
                assert part2.content == full.content[-32:]

                # 4. 起始范围请求（从 100 到末尾）
                part3 = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"Range": "bytes=100-"},
                )
                assert part3.status_code == 206
                assert part3.headers["content-range"] == f"bytes 100-{total_size - 1}/{total_size}"
                assert part3.content == full.content[100:]

                # 5. RFC 7233 §2.1 顺从：end 超过文件大小时自动钳位至末尾字节
                part_clamped = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"Range": f"bytes=0-{total_size + 9999}"},
                )
                assert part_clamped.status_code == 206
                assert part_clamped.headers["content-range"] == f"bytes 0-{total_size - 1}/{total_size}"
                assert part_clamped.headers["content-length"] == str(total_size)
                assert part_clamped.headers["content-disposition"] == 'attachment; filename="offline_package.zip"'
                assert part_clamped.content == full.content

                # 6. 负向：越界 Range 返回 416
                invalid_range = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"Range": f"bytes={total_size + 1000}-"},
                )
                assert invalid_range.status_code == 416
                assert invalid_range.headers["content-range"] == f"bytes */{total_size}"
                assert invalid_range.json()["detail"]["code"] == "RANGE_NOT_SATISFIABLE"

    asyncio.run(run())


def test_download_security_and_negative_paths(pg_uri, art_dir, engine_url):
    """负向测试：跨用户未授权拦截、磁盘篡改拦截、文件缺失拦截、租约访问。"""
    async def run():
        app = create_app(pg_uri, art_dir)
        async with app.router.lifespan_context(app):
            async with app.state.pool.acquire() as c:
                for t in TABLES:
                    await c.execute(f"delete from {t}")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://t"
            ) as client:
                ctx = await _publish_offline_experiment(client, pg_uri, art_dir, engine_url)
                cand_rev = ctx["cand_rev"]
                job_id = ctx["job_id"]
                zip_id = ctx["zip_id"]

                # 1. 未授权跨用户下载拦截
                r_unauth = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"X-Owner-Id": "teacher-intruder"},
                )
                assert r_unauth.status_code == 404, "跨用户下载未被隔离"
                assert r_unauth.json()["detail"]["code"] == "ARTIFACT_NOT_FOUND"

                # 2. 租约权限下载：持有该实验正在运行 job 的租约 token 可以下载
                async with app.state.pool.acquire() as c:
                    active_token = f"lease-{uuid.uuid4()}"
                    await c.execute(
                        """update jobs set lease_token = $2, lease_until = now() + interval '60 seconds', status = 'running'
                           where id = $1""",
                        job_id, active_token,
                    )
                r_lease = await client.get(
                    f"/api/v1/artifacts/{zip_id}/download",
                    headers={"X-Owner-Id": "other-agent", "X-Lease-Token": active_token},
                )
                assert r_lease.status_code == 200, "持有效租约 token 的下载被误杀"

                # 3. 磁盘篡改检测：修改盘上 ZIP 文件内容
                zip_disk = art_dir / "revisions" / str(cand_rev) / "offline_package.zip"
                original_bytes = zip_disk.read_bytes()
                zip_disk.write_bytes(original_bytes[:-10] + b"TAMPERED00")
                try:
                    r_tamper = await client.get(f"/api/v1/artifacts/{zip_id}/download")
                    assert r_tamper.status_code == 500
                    assert r_tamper.json()["detail"]["code"] == "CONTENT_HASH_MISMATCH"
                finally:
                    zip_disk.write_bytes(original_bytes)

                # 4. 文件缺失检测
                zip_backup = art_dir / "revisions" / str(cand_rev) / "offline_package.zip.bak"
                zip_disk.rename(zip_backup)
                try:
                    r_missing = await client.get(f"/api/v1/artifacts/{zip_id}/download")
                    assert r_missing.status_code == 404
                    assert r_missing.json()["detail"]["code"] == "ARTIFACT_FILE_MISSING"
                finally:
                    zip_backup.rename(zip_disk)

    asyncio.run(run())
