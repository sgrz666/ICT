"""Worker 主循环：领取一个任务并推进。

崩溃安全性来自三件事的组合：租约到期后别的 Worker 能接管；接管者依据 job_events
决定从哪个阶段接着走；执行期间心跳把租约续上（`worker/lease.py`），不然一个长任务
自己就把执行权睡丢了。崩掉的阶段会重跑（at-least-once），所以阶段步骤必须幂等
（外部动作用 job_id + 内容派生 id 做幂等键，§4.8）。

失败分三类，处理各不相同——把三者混成「一律 failed」是旧版的缺陷：

- **终态**（策略拒绝、验证不过、版本冲突、归属不符、超过重试或运行上限）：写 `failed`，
  不再重试。领域拒绝绝不能回去再调一次模型「幻想修复」。
- **可重试**（引擎/网络/数据库抖动）：退回 `queued` 并按有限退避写 `next_run_at`，
  `attempt` 由领取时递增，超过上限才终态化。
- **丢执行权 / 已取消**：什么状态都不改写（job 现在归别人，或教师已取消），
  只记一条事件就收手——继续写就是覆盖别人的执行记录。
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx

from eduforge.agent.policy import Rejected
from eduforge.application.coordinator import Coordinator
from eduforge.infrastructure.db.repositories import (
    LeaseLost,
    OwnershipConflict,
    RevisionConflict,
)
from eduforge.domain.errors import LeaseExpiredError
from eduforge.worker.errors import TerminalError
from eduforge.worker.lease import LeaseManager

# 阶段步骤里可能冒出来的「值得再试一次」的错：外部依赖抖动，不是业务判定。
# Engine Host 走 httpx、库走 asyncpg，两类都要覆盖到，否则网络故障会被当成崩溃。
RETRYABLE = (OSError, ConnectionError, httpx.TransportError, asyncpg.PostgresError)


class SimulatedCrash(Exception):
    """测试用：在某个阶段开始前中断进程，模拟崩在半路。"""


@dataclass
class Worker:
    repo: Any
    coordinator: Coordinator
    lease_seconds: int = 90
    steps_factory: Callable[..., dict] | None = None
    lease_pool: asyncpg.Pool | None = None
    heartbeat_seconds: float = 25.0
    max_attempts: int = 5
    backoff_seconds: tuple[float, ...] = (5.0, 15.0, 60.0)
    last_guard: LeaseManager | None = None

    async def run_once(self, *, crash_before: str | None = None) -> dict | None:
        token = f"w-{uuid.uuid4().hex[:8]}"
        job = await self.repo.claim(token, self.lease_seconds)
        if job is None:
            return None

        job_id = job["id"]
        if int(job["attempt"]) > self.max_attempts:
            # 无界重试会把同一个故障跑成死循环，还会把 attempt 变成噪声。
            await self.repo.append_event(
                job_id, stage=None, event_type="job_failed",
                payload={"code": "MAX_ATTEMPTS_EXCEEDED", "attempt": job["attempt"]},
            )
            status = await self.repo.mark_failed(job_id, token, "MAX_ATTEMPTS_EXCEEDED")
            return {"job_id": job_id, "failed": "MAX_ATTEMPTS_EXCEEDED", "status": status, "lease_token": token}

        guard = None
        if self.lease_pool is not None:
            guard = await LeaseManager.from_pool(
                self.lease_pool, job_id, token,
                heartbeat_interval_seconds=self.heartbeat_seconds,
                lease_duration_seconds=self.lease_seconds,
            )
            await guard.start()
        self.last_guard = guard

        if self.steps_factory is not None:
            # 租约到手才能把 lease_token 交给步骤：发布事务要靠它证明执行权（§3.5）
            self.coordinator.steps = self.steps_factory(token, guard)
        original = dict(self.coordinator.steps)

        def guarded(name, fn):
            async def inner(jid):
                if name == crash_before:
                    raise SimulatedCrash(name)
                return await fn(jid)
            return inner

        if crash_before is not None:
            self.coordinator.steps = {n: guarded(n, f) for n, f in original.items()}

        try:
            last = await self.coordinator.run(job_id, token)
        except LeaseExpiredError as e:
            # 取消或丢执行权：不改写 job 状态（那是别人的或教师已经说了停），
            # 也绝不发布。只留一条可见的事件。
            code = getattr(e, "code", "LEASE_LOST")
            await self.repo.append_event(
                job_id, stage=getattr(e, "stage", None), event_type="job_stopped",
                payload={"code": code, "detail": str(e)},
            )
            return {"job_id": job_id, "stopped": code, "lease_token": token}
        except (TerminalError, Rejected, RevisionConflict, OwnershipConflict, LeaseLost) as e:
            # 终态失败：重试不会改变结果，必须让任务可见地停下来。
            # 不这么做的话任务永远停在 running，教师前端只能转圈。
            if isinstance(e, RevisionConflict):
                code, stage = "REVISION_CONFLICT", "packaging"
            elif isinstance(e, OwnershipConflict):
                code, stage = "OWNERSHIP_CONFLICT", "packaging"
            elif isinstance(e, LeaseLost):
                code, stage = "LEASE_LOST", None
            else:
                code = getattr(e, "code", "TERMINAL")
                stage = getattr(e, "stage", None)
            await self.repo.append_event(
                job_id, stage=stage, event_type="job_failed", payload={"code": code, "detail": str(e)}
            )
            status = await self.repo.mark_failed(job_id, token, code)
            return {"job_id": job_id, "failed": code, "status": status, "lease_token": token}
        except RETRYABLE as e:
            # 外部依赖抖动：退回队列并有限退避，attempt 已在领取时计过。
            delay = self.backoff_seconds[min(int(job["attempt"]), len(self.backoff_seconds)) - 1]
            code = f"RETRY_{type(e).__name__}"
            await self.repo.append_event(
                job_id, stage=None, event_type="job_deferred",
                payload={"code": code, "detail": str(e), "delay_seconds": delay,
                         "attempt": job["attempt"]},
            )
            status = await self.repo.retry_later(job_id, token, delay_seconds=delay, error_code=code)
            return {"job_id": job_id, "deferred": code, "status": status, "lease_token": token}
        finally:
            self.coordinator.steps = original
            if guard is not None:
                await guard.aclose()

        await self.repo.set_stage(job_id, token, "done")
        return {"job_id": job_id, "last_stage": last, "lease_token": token}
