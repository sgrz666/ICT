"""Worker 主循环：领取一个任务并推进。

崩溃安全性来自两件事的组合：租约到期后别的 Worker 能接管，而接管者依据 job_events
决定从哪个阶段接着走。崩掉的那个阶段会重跑（at-least-once），所以阶段步骤必须幂等——
外部动作用 job_id + stage + attempt 做幂等键（§4.8）。
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from eduforge.agent.policy import Rejected
from eduforge.application.coordinator import Coordinator, Step
from eduforge.infrastructure.db.repositories import JobRepository, RevisionConflict
from eduforge.worker.errors import TerminalError


class SimulatedCrash(Exception):
    """测试用：在某个阶段开始前中断进程，模拟崩在半路。"""


@dataclass
class Worker:
    repo: JobRepository
    coordinator: Coordinator
    lease_seconds: int = 90
    steps_factory: Callable[[str], dict[str, Step]] | None = None

    async def run_once(self, *, crash_before: str | None = None) -> dict | None:
        token = f"w-{uuid.uuid4().hex[:8]}"
        job = await self.repo.claim(token, self.lease_seconds)
        if job is None:
            return None

        job_id = job["id"]
        if self.steps_factory is not None:
            # 租约到手才能把 lease_token 交给步骤：发布事务要靠它证明执行权（§3.5）
            self.coordinator.steps = self.steps_factory(token)
        original = dict(self.coordinator.steps)

        def guarded(name, fn):
            async def inner(jid):
                if name == crash_before:
                    raise SimulatedCrash(name)
                return await fn(jid)
            return inner

        if crash_before is not None:
            self.coordinator.steps = {
                n: guarded(n, f) for n, f in original.items()
            }
        try:
            last = await self.coordinator.run(job_id, token)
        except (TerminalError, Rejected, RevisionConflict) as e:
            # 终态失败：重试不会改变结果，必须让任务可见地停下来。
            # 不这么做的话任务永远停在 running，教师前端只能转圈。
            # 崩溃（SimulatedCrash）与网络/引擎不可用不在这里，它们该被别的 Worker 接管。
            if isinstance(e, RevisionConflict):
                code = "REVISION_CONFLICT"
                stage = "packaging"
            else:
                code = getattr(e, "code", "TERMINAL")
                stage = getattr(e, "stage", None)
            await self.repo.append_event(job_id, stage=stage,
                                         event_type="job_failed", payload={"code": code, "detail": str(e)})
            status = await self.repo.mark_failed(job_id, token, code)
            return {"job_id": job_id, "failed": code, "status": status, "lease_token": token}
        finally:
            self.coordinator.steps = original

        await self.repo.set_stage(job_id, token, "done")
        return {"job_id": job_id, "last_stage": last, "lease_token": token}
