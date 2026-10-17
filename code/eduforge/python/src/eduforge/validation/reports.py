"""验证报告：把"检查项"与"结论"分开存，发布只认结论。

Gate C §C.1/§C.2 起，每条检查必须交代**证据从哪来**（`source`）与**在什么科学
profile 下才成立**（`profile`），并且三态化：观测支持叫 `pass`、观测反驳叫 `fail`、
**根本没有独立观测叫 `na`**。`na` 不参与"全过"的判定，它把结论压成 `inconclusive`——
这一条存在的全部理由就是：旧实现拿 `u < f`、`abs(f-u) < 1e-4` 这种公式恒真式
给虚像和无穷远工况盖 `passed`，那是公式在给自己作证。

报告还绑定候选：`candidate_id` + `content_hash` + `engine_version` + `profile`。
「验证什么就发布什么」要有可核对的凭据，不能靠"时间上是同一次运行"。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

Verdict = Literal["passed", "failed", "inconclusive"]
CheckStatus = Literal["pass", "fail", "na"]


@dataclass
class Check:
    id: str
    passed: bool
    observed: Any = None
    expected: Any = None
    detail: str = ""
    # 证据来源：engine:* 表示来自上游真实仿真的读数，reference:* 表示独立公式，
    # catalog:* 表示清单/登记事实。没有来源的判据不算证据。
    source: str = "engine:measurement"
    # 该判据成立的科学 profile（如 thin_lens_ideal）。换引擎/换透镜类型必须显式失效。
    profile: str = "thin_lens_ideal"
    # 三态：观测支持 / 观测反驳 / 无独立观测（不可判）
    status: CheckStatus | None = None
    # 分辨率与容差的依据要写出来，别让"对上了"看起来像精确命中
    tolerance: str = ""
    # 是否参与结论判定。实像工况另有决定性观测（哪块屏最清晰 +
    # 光斑是否真的聚焦），交点拟合只是第二件量具；虚像与无穷远没有别的量具，
    # 所以那里的 na 必须决定结论。
    decisive: bool = True

    def __post_init__(self) -> None:
        if self.status is None:
            self.status = "pass" if self.passed else "fail"
        # passed 与 status 必须同向，否则报告与结论会各说一套
        elif self.passed != (self.status == "pass"):
            raise ValueError(f"{self.id}: passed 与 status 不一致")

    @property
    def is_unverifiable(self) -> bool:
        return self.status == "na"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "passed": self.passed, "status": self.status,
            "observed": self.observed, "expected": self.expected, "detail": self.detail,
            "source": self.source, "profile": self.profile, "tolerance": self.tolerance,
        }


@dataclass
class ValidationReport:
    job_id: str
    checks: list[Check] = field(default_factory=list)
    verdict: Verdict = "inconclusive"
    candidate_id: UUID | str | None = None
    content_hash: str | None = None
    engine_version: str | int | None = None
    profile: str = "thin_lens_ideal"

    def add(self, check: Check) -> None:
        self.checks.append(check)

    def finalize(self) -> Verdict:
        """无检查项时结论是 inconclusive，不是 passed —— 没验过不能算过。

        有 `na`（无独立观测）时也不能给 passed：观测不到就是观测不到，
        把它折算成失败同样不对（会被读成"物理不成立"），所以停在 inconclusive。
        """
        decisive = [c for c in self.checks if c.decisive]
        if not self.checks:
            self.verdict = "inconclusive"
        elif any(c.status == "fail" for c in self.checks):
            self.verdict = "failed"
        elif any(c.status == "na" for c in decisive):
            self.verdict = "inconclusive"
        elif all(c.status == "pass" for c in decisive):
            self.verdict = "passed"
        else:
            self.verdict = "inconclusive"
        return self.verdict

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id, "verdict": self.verdict,
            "candidate_id": str(self.candidate_id) if self.candidate_id else None,
            "content_hash": self.content_hash,
            "engine_version": str(self.engine_version) if self.engine_version is not None else None,
            "profile": self.profile,
            "checks": [c.as_dict() for c in self.checks],
        }
