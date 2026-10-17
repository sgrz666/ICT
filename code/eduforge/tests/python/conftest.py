"""共享夹具：起真实 Engine Host 子进程。

不是 mock：Python 侧不解释实验 JavaScript，链路要真就必须真起那个 Node 进程。
`test_publish_chain.py` 里原本自带一份同样的启动代码，新用例统一到这一份。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import warnings
import time
from pathlib import Path

import httpx
import pytest

ENGINE_DIR = Path(__file__).resolve().parents[2] / "services" / "engine-host"

# 测试专用临时目录前缀。夹具自己 mkdtemp 起 Postgres 与产物目录，
# 但只 stop 服务器、不删目录——2026-10-17 用户抱怨 %TEMP% 一天之内堆出上千个目录
# （每个簇几十 MB、每份离线包 2163 个文件）。见下面的会话级清扫夹具。
_TEST_TMP_PREFIXES = ("eduforge-", "pkg-verify-", "verify-smoke-", "verify-probe-", "race-")


@pytest.fixture(scope="session", autouse=True)
def _sweep_own_temp_dirs():
    """跑之前和之后各扫一遍，把测试临时目录留在 %TEMP% 的数量压到"当前还有进程抓着"的那些。

    各夹具自己 `pgserver.get_server(mkdtemp(), cleanup_mode=None)`，只 stop 服务器不删目录；
    Windows 上 `stop()` 还常常慢一拍，于是 2026-10-17 一天之内 %TEMP% 堆出上千个
    `eduforge-*`（每簇几十 MB，每份离线包 2163 个文件）。这里只动**测试前缀**的目录，
    别人的临时文件一律不碰；删不掉就如实 warn，而不是假装干净。
    """
    tmp = Path(tempfile.gettempdir())

    def candidates() -> list[Path]:
        try:
            return [p for p in tmp.iterdir() if p.is_dir() and p.name.startswith(_TEST_TMP_PREFIXES)]
        except OSError:
            return []

    def sweep(keep: set[str] = frozenset(), older_than: float | None = None) -> list[Path]:
        now = time.time()
        left: list[Path] = []
        for p in candidates():
            if p.name in keep:
                continue
            # 只碰"确定不在别人手里"的：开场那遍要求目录已经闲了 30 分钟以上，
            # 因为同一台机器上可能有另一个会话正在跑测试，它的前缀和这里一样。
            if older_than is not None and now - p.stat().st_mtime < older_than:
                continue
            shutil.rmtree(p, ignore_errors=True)
            if p.exists():
                left.append(p)
        return left

    # 开场先清历史遗留（30 分钟内的不动，避免误删并行会话正在用的目录）
    sweep(older_than=1800)
    before = {p.name for p in candidates()}
    yield
    for attempt in range(2):
        left = [p for p in sweep(before) if p.exists()]
        if not left:
            return
        if attempt == 0:
            time.sleep(1.5)  # 刚 stop 的 Postgres 可能还要几百毫秒才放开目录
        warnings.warn(
            f"仍有 {len(left)} 个测试临时目录删不掉（多半还有进程抓着）："
            + ", ".join(p.name for p in left[:5]),
            RuntimeWarning,
            stacklevel=2,
        )


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_engine(extra_env: dict[str, str] | None = None) -> tuple[str, subprocess.Popen]:
    if not (ENGINE_DIR / "dist" / "main.js").exists():
        subprocess.run(
            ["node_modules/.bin/tsc", "-p", "tsconfig.build.json"],
            cwd=ENGINE_DIR, check=True,
        )
    port = free_port()
    proc = subprocess.Popen(
        ["node", "dist/main.js"],
        cwd=ENGINE_DIR,
        env={
            **os.environ,
            "ENGINE_HOST_PORT": str(port),
            "NODE_ENV": "production",
            **(extra_env or {}),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/healthz", timeout=2).status_code == 200:
                return base, proc
        except Exception:
            time.sleep(0.3)
    out = proc.stdout.read() if proc.stdout else ""
    proc.kill()
    pytest.fail(f"engine-host 未就绪：\n{out}")
    raise AssertionError("unreachable")


@pytest.fixture(scope="module")
def engine_url():
    base, proc = start_engine()
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
