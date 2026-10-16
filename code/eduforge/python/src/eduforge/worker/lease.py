"""任务租约管理与执行权校验。

对齐方案 §1.2 和 §4.8：
- 周期性心跳续租（默认 30s 周期，租约 90s）；
- 严格携带 lease_token 校验执行权；
- 租约过期自动标记失效并停止当前执行，防止双 Worker 脑裂执行。
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from eduforge.domain.errors import LeaseExpiredError
from eduforge.domain.ports import JobRepositoryPort


class LeaseManager:
    """Worker 任务租约守护器。"""

    def __init__(
        self,
        repository: JobRepositoryPort,
        job_id: UUID,
        lease_token: str,
        heartbeat_interval_seconds: int = 30,
        lease_duration_seconds: int = 90,
    ):
        self.repository = repository
        self.job_id = job_id
        self.lease_token = lease_token
        self.heartbeat_interval = heartbeat_interval_seconds
        self.lease_duration = lease_duration_seconds
        self._running = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._expired = False

    async def start(self) -> None:
        """启动后台心跳协程。"""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """停止心跳协程。"""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    def check_active(self) -> None:
        """检查租约是否仍然有效，若已失效立即抛出 LeaseExpiredError。"""
        if self._expired:
            raise LeaseExpiredError(
                f"任务 {self.job_id} 租约已过期或被抢占，当前 Worker 已丧失执行权。",
                code="LEASE_LOST",
            )

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                success = await self.repository.heartbeat(
                    job_id=self.job_id,
                    lease_token=self.lease_token,
                    lease_seconds=self.lease_duration,
                )
                if not success:
                    self._expired = True
                    self._running = False
                    break
            except asyncio.CancelledError:
                break
            except Exception:
                # 遇到非取消网络异常先不立即判定丢失，留给重试
                pass
