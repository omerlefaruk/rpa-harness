"""Shared execution trace and verification bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from harness.security import redact_value


@dataclass
class StepCheck:
    passed: bool
    message: str = ""
    expected: Any = None
    actual: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_value(
            {
                "passed": self.passed,
                "message": self.message,
                "expected": self.expected,
                "actual": self.actual,
                "evidence": self.evidence,
            }
        )


@dataclass
class ExecutionStep:
    index: int
    description: str
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    duration_ms: float = 0.0
    checks: list[StepCheck] = field(default_factory=list)
    error: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def finish(self, status: str, error: str | None = None) -> None:
        self.status = status
        self.error = error
        self.ended_at = datetime.now()
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000

    def to_dict(self) -> dict[str, Any]:
        return redact_value(
            {
                "index": self.index,
                "description": self.description,
                "status": self.status,
                "started_at": self.started_at.isoformat(),
                "ended_at": self.ended_at.isoformat() if self.ended_at else None,
                "duration_ms": self.duration_ms,
                "verified": self.verified,
                "checks": [check.to_dict() for check in self.checks],
                "error": self.error,
                "evidence": self.evidence,
            }
        )


class ExecutionTrace:
    """Runner-neutral trace of step and check outcomes."""

    def __init__(self) -> None:
        self.steps: list[ExecutionStep] = []
        self.current_step: ExecutionStep | None = None
        self.last_successful_step: ExecutionStep | None = None
        self.failed_step: ExecutionStep | None = None

    def start_step(self, description: str, index: int | None = None) -> ExecutionStep:
        if self.current_step and self.current_step.status == "running":
            self.finish_current("passed")
        step = ExecutionStep(index=index or len(self.steps) + 1, description=description)
        self.steps.append(step)
        self.current_step = step
        return step

    def record_check(
        self,
        passed: bool,
        message: str = "",
        expected: Any = None,
        actual: Any = None,
        evidence: dict[str, Any] | None = None,
    ) -> StepCheck:
        if not self.current_step:
            self.start_step("implicit verification")
        assert self.current_step is not None
        check = StepCheck(
            passed=passed,
            message=message,
            expected=expected,
            actual=actual,
            evidence=evidence or {},
        )
        self.current_step.checks.append(check)
        return check

    def finish_current(self, status: str, error: str | None = None) -> None:
        if not self.current_step:
            return
        self.current_step.finish(status, error=error)
        if status == "passed":
            self.last_successful_step = self.current_step
        elif status == "failed":
            self.failed_step = self.current_step

    @property
    def total_checks(self) -> int:
        return sum(len(step.checks) for step in self.steps)

    @property
    def unverified_steps(self) -> list[ExecutionStep]:
        return [step for step in self.steps if not step.checks]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "last_successful_step": (
                self.last_successful_step.to_dict() if self.last_successful_step else None
            ),
            "failed_step": self.failed_step.to_dict() if self.failed_step else None,
            "verification": {
                "total_checks": self.total_checks,
                "unverified_steps": [step.description for step in self.unverified_steps],
            },
        }
