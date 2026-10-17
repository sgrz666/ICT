"""Worker 任务租约守护器（心跳续租 + 执行权判定）。

这一轮才真正接线（Gate B §B.1–B.2）。此前它调的是 `JobRepository.heartbeat`，
而持久层从来没有这个方法——所以「有心跳」只是文档说法，真实行为是**租约从不续期**：
默认 90s 的租约，遇上真模型多轮循环必然过期，任务在执行中途变成别的 Worker
可领取的了，最后在原 Worker 手里撞 `LeaseLost`。

三条判据都落在 SQL 里（见 `JobRepository.renew_and_check`）：

1. 只有 `status='running'` 且 `lease_token` 仍是自己的，才允许续租；
2. **过期之后不许把自己续回合法**（`lease_until > now()` 必须在续之前成立），
   否则「先睡着让租约过期、再续回来接着干」就绕过了抢占语义；
3. 取消单独回报：它不是失败，不该重试，但必须立刻停止新动作与发布。

心跳必须走**独立连接**：Worker 执行 Agent SQL 用的是同一条 `asyncpg.Connection`，
asyncpg 的连接不允许并发查询，后台心跳与之共用就会互相打断（本轮改成从池里
单独 acquire 一条，专用给守护器）。
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg

from eduforge.domain.errors import LeaseExpiredError
from eduforge.infrastructure.db.repositories import JobRepository

# 状态词与 `renew_and_check` 的回报一一对应；`unstarted`/`running` 是守护器自身的阶段。
OK = "ok"


class LeaseManager:
    """一个任务一个守护器：续租、判定执行权、超时与取消协作式中止。"""

    def __init__(
        self,
        repository: Any,
        job_id: UUID,
        lease_token: str,
        *,
        heartbeat_interval_seconds: float = 25.0,
        lease_duration_seconds: int = 90,
        max_runtime_seconds: float | None = 900.0,
    ) -> None:
        self.repository = repository
        self.job_id = job_id
        self.lease_token = lease_token
        self.heartbeat_interval = heartbeat_interval_seconds
        self.lease_duration = lease_duration_seconds
        self.max_runtime_seconds = max_runtime_seconds
        self.state = "unstarted"
        self.renewals = 0
        self._running = False
        self._expired = False          # 兼容旧断言语义：执行权是否已不在自己手上
        self._task: asyncio.Task[None] | None = None
        self._started_monotonic: float | None = None
        self._pool: asyncpg.Pool | None = None
        self._own_conn: asyncpg.Connection | None = None

    @classmethod
    async def from_pool(
        cls, pool: asyncpg.Pool, job_id: UUID, lease_token: str, **kwargs: Any
    ) -> "LeaseManager":
        """从连接池单独拿一条连接给心跳用——不与 Worker 的 Agent SQL 抢同一条。"""
        conn = await pool.acquire()
        mgr = cls(JobRepository(conn), job_id, lease_token, **kwargs)
        mgr._pool = pool
        mgr._own_conn = conn
        return mgr

    async def aclose(self) -> None:
        await self.stop()
        if self._pool is not None and self._own_conn is not None:
            await self._pool.release(self._own_conn)
            self._own_conn = None

    async def start(self) -> None:
        """先立刻续一次再放后台循环：开局就丢执行权的任务不该往下跑。"""
        await self.beat()
        self._running = True
        self._started_monotonic = asyncio.get_running_loop().time()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def beat(self) -> str:
        """一次续租 + 状态判定。测试用它把时间推进变成可观察的事件。"""
        self.state = await self.repository.renew_and_check(
            self.job_id, self.lease_token, self.lease_duration
        )
        if self.state != OK:
            self._expired = True
            self._running = False
        else:
            self.renewals += 1
        return self.state

    def check_active(self) -> None:
        """新动作前的一闸门：丢权/取消/超时都必须立刻停下。"""
        if self.state == "cancelled":
            raise LeaseExpiredError(
                f"任务 {self.job_id} 已被教师取消，停止后续动作与发布。", code="JOB_CANCELLED"
            )
        if self.state == "timeout":
            raise LeaseExpiredError(
                f"任务 {self.job_id} 超过单任务最长运行时长，按失败收。", code="RUN_TIMEOUT"
            )
        if self._expired:
            raise LeaseExpiredError(
                f"任务 {self.job_id} 租约已过期或被抢占（{self.state}），当前 Worker 已丧失执行权。",
                code="LEASE_LOST",
            )

    async def check_now(self) -> str:
        """发布前的强校验：当场问一次库，不吃后台心跳的旧结论。"""
        state = await self.beat()
        self.check_active()
        return state

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.heartbeat_interval)
            if not self._running:
                break
            if (
                self.max_runtime_seconds is not None
                and self._started_monotonic is not None
                and asyncio.get_running_loop().time() - self._started_monotonic > self.max_runtime_seconds
            ):
                self.state = "timeout"
                self._expired = True
                break
            try:
                if (await self.beat()) != OK:
                    break
            except asyncio.CancelledError:
                break
            except Exception:
                # 一次网络抖动不等于丢权：留给下一次心跳，真正判定在 SQL 里。
                # 但连续失败不能无限静默——租约到点自然过期，届时 SQL 判定为 expired。
                continue
