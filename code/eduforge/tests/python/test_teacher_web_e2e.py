"""切片 8 金路径：真实浏览器驱动教师前端，走完 §6.1 那条使用链。

起的是真东西：pgserver 的真实 Postgres、uvicorn 起的业务 API、node 起的
Engine Host + 浏览器网关（同源）、`python -m eduforge.worker.run` 的 Worker 进程，
以及 `vite build` 出来的前端产物。只有规划是命令行注入的固定提案。

判据是可证的：预览 iframe 里上游模拟器真的算出了光、下载文件的哈希与产物清单登记值一致、
失败任务在界面上说得出人话而不是转圈。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asyncpg
import httpx
import pgserver
import pytest
from conftest import free_port, start_engine
from playwright.sync_api import sync_playwright

from eduforge.infrastructure.db.repositories import artifact_id_for

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "apps" / "teacher-web"
DIST = APP_DIR / "dist"

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


def _u(value) -> uuid.UUID:
    """asyncpg 给 UUID、HTTP 给 str；断言里不想再区分。"""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _run_async(go):
    """Playwright 同步 API 自己占着事件循环，asyncio.run 只能换个线程跑。"""
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(go())).result()


def _wait_http(url: str, timeout_s: float = 40) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3).status_code < 500:
                return
        except Exception:
            time.sleep(0.3)
    raise AssertionError(f"服务没起来：{url}")


@pytest.fixture(scope="module")
def stack():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-e2e-"), cleanup_mode=None)
    uri = server.get_uri()
    art = Path(tempfile.mkdtemp(prefix="eduforge-e2e-art-"))

    if not (DIST / "index.html").exists():
        subprocess.run(
            ["node", str(APP_DIR / "node_modules" / "vite" / "bin" / "vite.js"), "build"],
            cwd=APP_DIR, check=True,
        )

    api_port = free_port()
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "eduforge.api.serve:app",
         "--host", "127.0.0.1", "--port", str(api_port), "--log-level", "warning"],
        env={**os.environ, "EDUFORGE_DSN": uri, "EDUFORGE_ARTIFACT_DIR": str(art)},
    )
    api_base = f"http://127.0.0.1:{api_port}"
    try:
        _wait_http(f"{api_base}/api/v1/templates")

        gateway_port = free_port()
        engine_base, engine_proc = start_engine({
            "ENGINE_GATEWAY_PORT": str(gateway_port),
            "EDUFORGE_API_URL": api_base,
            "EDUFORGE_TEACHER_WEB_DIST": str(DIST),
        })
        gateway = f"http://127.0.0.1:{gateway_port}"
        try:
            _wait_http(f"{gateway}/")
            yield {
                "uri": uri, "art": art, "api": api_base, "engine": engine_base,
                "gateway": gateway, "tmp": Path(tempfile.mkdtemp(prefix="eduforge-e2e-dl-")),
            }
        finally:
            engine_proc.terminate()
            try:
                engine_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                engine_proc.kill()
    finally:
        api_proc.terminate()
        try:
            api_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            api_proc.kill()
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


def _worker(stack, *, entity: str = "lens_1", focal: str = "15"):
    """按测试启停 Worker：两个 Worker 同时在跑会抢任务，抢不到的一方就变成随机失败。"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "eduforge.worker.run",
         "--planner-static-focal", focal, "--planner-static-entity", entity,
         "--dsn", stack["uri"], "--engine-url", stack["engine"],
         "--artifact-dir", str(stack["art"]), "--lease-seconds", "20", "--idle-seconds", "0.5"],
        env={**os.environ, "DEEPSEEK_API_KEY": "", "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc



def _candidate_revision_of(uri: str, job_id) -> "uuid.UUID":
    """读生产写下的候选版本 id：这就是「页面上那个版本确实由这条链发出」的凭据。"""
    async def go():
        c = await asyncpg.connect(uri)
        try:
            return await c.fetchval("select candidate_revision_id from jobs where id = $1", job_id)
        finally:
            await c.close()
    return _run_async(go)


def _latest_experiment(uri: str) -> dict:
    async def go():
        c = await asyncpg.connect(uri)
        try:
            # experiments 表没有时间戳列，"最近一个实验"只能按它 head 版本的落地时间排
            row = await c.fetchrow(
                """select e.id, e.head_revision_id, r.created_at
                   from experiments e
                   join experiment_revisions r on r.id = e.head_revision_id
                   order by r.created_at desc limit 1"""
            )
            all_revs = await c.fetch(
                "select id from experiment_revisions where experiment_id = $1 order by created_at", row["id"]
            )
            arts = await c.fetchrow(
                "select a.sha256, a.id as artifact_id from artifacts a "
                "join experiment_revisions r on r.id = a.revision_id where r.experiment_id = $1",
                row["id"],
            )
            return {
                "experiment_id": str(row["id"]),
                "head": str(row["head_revision_id"]),
                "revision_count": len(all_revs),
                "revisions": [str(r["id"]) for r in all_revs],
                "artifact": dict(arts) if arts else None,
            }
        finally:
            await c.close()

    return _run_async(go)


def test_golden_path_selects_submits_previews_and_downloads(stack):
    worker = _worker(stack)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 950})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            page.goto(f"{stack['gateway']}/", wait_until="load")
            # 模板清单来自真实 catalog；按钮文本就是 manifest 里的 title
            page.get_by_role("button", name="凸透镜成像").click()
            page.wait_for_selector("text=当前实验", timeout=15000)
            page.get_by_role("button", name="提交给 Agent").click()

            # 桥接的 ready 落到界面上，才算"预览显示的是已验证版本"
            page.wait_for_function(
                "() => document.body.innerText.includes('已载入版本')", timeout=120000
            )

            sims = [f for f in page.frames if "/simulator/" in (f.url or "")]
            assert sims, "预览 iframe 里没有上游模拟器，说明渲染不是上游产出的"
            sim = sims[0]
            assert "射线光学模拟" in sim.title()
            # 光层要有实际像素：场景载入却不发光，说明仿真根本没跑
            assert sim.evaluate(LIT_PIXELS) > 0

            # 版本区：种子 + 新发布的这一个，head 指向新的
            body = page.inner_text("body")
            assert "· head" in body
            assert page.locator("table tbody tr").count() == 2

            # 下载：浏览器存盘后由测试本地重算，与产物清单登记值比对
            with page.expect_download(timeout=30000) as info:
                page.get_by_role("button", name="下载原生场景").click()
            download = info.value
            saved = stack["tmp"] / download.suggested_filename
            download.save_as(saved)

            latest = _latest_experiment(stack["uri"])
            assert latest["revision_count"] == 2, latest
            assert latest["artifact"], "发布成功却没有登记产物"
            bytes_ = saved.read_bytes()
            assert hashlib.sha256(bytes_).hexdigest() == latest["artifact"]["sha256"], \
                "界面提示已校验，但落盘字节和登记哈希不一致"

            # head 与产物指向必须与那次任务对得上：证明页面上那个版本确实是这条链发出来的
            job_row = _job_for(stack["uri"], _u(latest["experiment_id"]))
            assert job_row and job_row["status"] == "succeeded", job_row
            job_id = _u(job_row["id"])
            # Gate A 之后候选版本 id 由内容哈希派生（同一 job 的连续编辑各自成版），
            # 用例读生产写进 jobs.candidate_revision_id 的那一个，而不是自己拼 id。
            cand = _candidate_revision_of(stack["uri"], job_id)
            assert _u(latest["head"]) == cand, "head 必须前进到本 job 的候选版本"
            assert _u(latest["artifact"]["artifact_id"]) == artifact_id_for(
                job_id, "native", latest["artifact"]["sha256"])

            # 验证版本回滚（§6.1/§6.2 闭环）：点击回滚到种子版本
            rollback_btn = page.get_by_role("button", name="回滚到此版本")
            assert rollback_btn.count() == 1
            rollback_btn.click()
            page.wait_for_function(
                "() => { const rows = document.querySelectorAll('table tbody tr'); "
                "return rows.length === 2 && rows[0].innerText.includes('head'); }",
                timeout=15000,
            )
            after_rollback = _latest_experiment(stack["uri"])
            assert _u(after_rollback["head"]) != _u(latest["head"])
            assert _u(after_rollback["head"]) == _u(after_rollback["revisions"][0])

            assert page_errors == [], f"页面报错：{page_errors}"
            browser.close()
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()


def _job_for(uri: str, experiment_id):
    async def go():
        c = await asyncpg.connect(uri)
        try:
            row = await c.fetchrow(
                "select id, status, candidate_revision_id from jobs where experiment_id = $1 "
                "order by created_at desc limit 1", experiment_id
            )
            return dict(row) if row else None
        finally:
            await c.close()

    return _run_async(go)


def test_rejected_edit_is_explained_not_spinning(stack):
    """策略拒绝要在界面上说得出原因。只有转圈的 Demo 等于把失败藏起来。"""
    worker = _worker(stack, entity="lens_9")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 950})
            page.goto(f"{stack['gateway']}/", wait_until="load")
            page.get_by_role("button", name="凸透镜成像").click()
            page.wait_for_selector("text=当前实验", timeout=15000)
            page.locator("textarea").fill("把那个没登记过的透镜焦距改成 15 厘米")
            page.get_by_role("button", name="提交给 Agent").click()

            page.wait_for_function(
                "() => document.body.innerText.includes('PARAMETER_NOT_REGISTERED')", timeout=90000
            )
            body = page.inner_text("body")
            assert "不在这个模板的登记清单里" in body, body[-500:]
            # 失败不产出版本：历史里只有种子，head 也没动
            assert page.locator("table tbody tr").count() == 1
            assert "已载入版本" not in body
            browser.close()
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
