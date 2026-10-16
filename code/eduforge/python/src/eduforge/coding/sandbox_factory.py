"""OpenSandbox 工厂与环境初始化。

对齐方案 §1.2 和 §4.6：
- 创建受限任务执行沙箱；
- 预装固定工具链与安全限制；
- 在无 Docker 守护进程或缺少 OpenSandbox 时抛出清晰的配置异常。
"""
from __future__ import annotations

import os
from typing import Any

from eduforge.domain.errors import EduForgeError


class SandboxFactory:
    """沙箱容器生成工厂。"""

    def __init__(self, image: str = "eduforge-sandbox:latest"):
        self.image = image

    def create_sandbox(self) -> Any:
        """创建沙箱实例。若未装 opensandbox 或无 Docker 则抛出明确错误。"""
        try:
            from opensandbox import SandboxSync
        except ImportError as exc:
            raise EduForgeError(
                "未安装 opensandbox 库。运行切片 7 需要 opensandbox 与 Docker 守护进程支持。",
                code="SANDBOX_DEPENDENCY_MISSING",
            ) from exc

        # 检查 Docker 管道或配置
        docker_host = os.getenv("DOCKER_HOST")
        try:
            return SandboxSync(
                image=self.image,
                network_disabled=True,  # 任务沙箱禁用外部网络访问，防数据泄露
            )
        except Exception as exc:
            raise EduForgeError(
                f"无法连接 Docker 守护进程创建执行沙箱: {exc}。请确认 Docker Desktop 正在运行。",
                code="DOCKER_UNAVAILABLE",
            ) from exc
