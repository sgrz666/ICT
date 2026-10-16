"""共享夹具：起真实 Engine Host 子进程。

不是 mock：Python 侧不解释实验 JavaScript，链路要真就必须真起那个 Node 进程。
`test_publish_chain.py` 里原本自带一份同样的启动代码，新用例统一到这一份。
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

ENGINE_DIR = Path(__file__).resolve().parents[2] / "services" / "engine-host"


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
