"""Deep Agents 代码定制执行器。

对齐方案 §4.6 完整规格：
- 使用受限沙箱执行代码级定制任务；
- 真实模型密钥不落盘到任务文件；
- 最终仅回收白名单指定的 src/lesson.ts 与 src/controls.ts；
- 外部依赖未就绪时抛出明确领域异常。
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from eduforge.coding.budget import ExecutionBudget
from eduforge.domain.errors import EduForgeError

EXPORT_PATHS = [
    "/workspace/src/lesson.ts",
    "/workspace/src/controls.ts",
]


async def customize(
    *,
    model: Any,
    create_sandbox: Callable[[], Any],
    input_files: list[tuple[str, bytes]],
    instruction: str,
    budget: ExecutionBudget = ExecutionBudget(),
) -> dict[str, bytes]:
    """在隔离沙箱中运行 Deep Agent 定制代码。"""
    try:
        from deepagents import create_deep_agent
        from langchain_opensandbox import OpenSandboxBackend
    except ImportError as exc:
        raise EduForgeError(
            "未安装 deepagents 或 langchain_opensandbox。此功能需要安装完整切片 7 依赖。",
            code="DEEP_AGENTS_DEPENDENCY_MISSING",
        ) from exc

    sandbox = await asyncio.to_thread(create_sandbox)

    try:
        backend = OpenSandboxBackend(
            sandbox=sandbox,
            timeout=60,
        )

        await asyncio.to_thread(
            backend.upload_files,
            input_files,
        )

        agent = create_deep_agent(
            model=model,
            backend=backend,
            tools=[],
            system_prompt=(
                "你负责修改已有教学实验的包装与交互。"
                "根据提供的接口完成任务。"
                "最终交付文件为 src/lesson.ts 和 src/controls.ts。"
                "请说明完成内容和验证结果。"
            ),
        )

        async with asyncio.timeout(budget.max_duration_seconds):
            await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": instruction,
                        }
                    ]
                },
                config={"recursion_limit": budget.max_turns},
            )

        downloaded = await asyncio.to_thread(
            backend.download_files,
            EXPORT_PATHS,
        )
        return dict(downloaded) if isinstance(downloaded, list) else downloaded
    finally:
        await asyncio.to_thread(sandbox.destroy)
