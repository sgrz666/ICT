"""Engine Host 的 HTTP 客户端。

Python 不解释实验 JavaScript：所有场景解释与仿真都在 Engine Host / 上游核心里发生，
这一层只负责传请求和取回度量。
"""
from __future__ import annotations

from typing import Any

import httpx


class EngineUnavailable(Exception):
    pass


class EditRejected(Exception):
    """Engine Host 拒绝该修改（上游 loadJSON 不认，或量程不符）。"""

    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        super().__init__(f"engine rejected with {status}: {payload}")
        self.status = status
        self.payload = payload


class EngineClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    async def template(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.get(f"{self.base}/adapters/ray_optics/template")
            if r.status_code != 200:
                raise EngineUnavailable(f"template endpoint -> {r.status_code}")
            return r.json()

    async def apply(self, native: dict, edit: dict) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(
                f"{self.base}/adapters/ray_optics/apply",
                json={"native": native, "edit": edit},
            )
            if r.status_code == 422:
                raise EditRejected(r.status_code, r.json())
            if r.status_code == 400:
                raise EditRejected(r.status_code, r.json())
            if r.status_code != 200:
                raise EngineUnavailable(f"apply -> {r.status_code}")
            return r.json()


def sharpest_screen(result: dict[str, Any]) -> dict[str, Any] | None:
    """从 Engine Host 的读数里取实测像面。

    判据与 TS 侧保持一致：先按捕获功率下限剔除漏检导致的退化读数，
    再取光斑二矩半径最小者。peak_share 不可用（远屏假清晰）。
    """
    usable = [
        p for p in result["measurement"]["probes"]
        if (p.get("power_fraction") or 0) >= 0.2 and p.get("rms_units") is not None
    ]
    if not usable:
        return None
    return min(usable, key=lambda p: p["rms_units"])
