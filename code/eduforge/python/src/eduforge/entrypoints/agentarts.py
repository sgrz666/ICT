"""华为云 AgentArts 运行时入口（§6.3）。

本地与云端迁移时共用同一个 build_planner()。
当运行在华为云 AgentArts 容器时通过 AgentArtsRuntimeApp 驱动。
"""
from __future__ import annotations

import os
from typing import Any

from eduforge.agent.bootstrap import build_planner
from eduforge.domain.contracts import PlannerRequest


# 支持在华为云 AgentArts 环境加载 SDK，未安装时提供兼容模式以便本地检查
try:
    from agentarts.sdk import AgentArtsRuntimeApp  # type: ignore
except ImportError:
    class AgentArtsRuntimeApp:  # type: ignore
        def __init__(self):
            self._handler = None

        def entrypoint(self, fn):
            self._handler = fn
            return fn

        def run(self):
            print("[AgentArtsRuntimeApp] Running in compatibility mode (SDK not installed)")

        async def invoke_handler(self, payload: dict) -> dict:
            if self._handler is None:
                raise RuntimeError("No entrypoint registered")
            return await self._handler(payload)


app = AgentArtsRuntimeApp()
planner = None


def get_planner():
    global planner
    if planner is None:
        planner = build_planner()
    return planner


def set_planner(custom_planner):
    global planner
    planner = custom_planner


@app.entrypoint
async def handler(payload: dict) -> dict:
    request = PlannerRequest.model_validate(payload)
    p = get_planner()
    result = await p.ainvoke(
        {"request": request},
        config={"recursion_limit": 12},
    )
    return result["work_order"].model_dump(mode="json")


if __name__ == "__main__":
    app.run()
