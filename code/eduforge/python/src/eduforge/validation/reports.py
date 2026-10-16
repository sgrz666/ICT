"""验证报告：把"检查项"与"结论"分开存，发布只认结论。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Verdict = Literal["passed", "failed", "inconclusive"]


@dataclass
class Check:
    id: str
    passed: bool
    observed: Any = None
    expected: Any = None
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "passed": self.passed,
            "observed": self.observed, "expected": self.expected, "detail": self.detail,
        }


@dataclass
class ValidationReport:
    job_id: str
    checks: list[Check] = field(default_factory=list)
    verdict: Verdict = "inconclusive"

    def add(self, check: Check) -> None:
        self.checks.append(check)

    def finalize(self) -> Verdict:
        """无检查项时结论是 inconclusive，不是 passed —— 没验过不能算过。"""
        if not self.checks:
            self.verdict = "inconclusive"
        elif all(c.passed for c in self.checks):
            self.verdict = "passed"
        elif any(not c.passed and c.expected is not None for c in self.checks):
            self.verdict = "failed"
        else:
            self.verdict = "inconclusive"
        return self.verdict

    def as_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "verdict": self.verdict, "checks": [c.as_dict() for c in self.checks]}
