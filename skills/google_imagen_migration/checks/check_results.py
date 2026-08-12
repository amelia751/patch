"""Result types shared by every check module.

A check never raises for a policy outcome: it returns a result. Only an
unreadable input is exceptional, because that is an operator error rather than a
finding about the change under review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class Verdict(str, Enum):
    # The skill's own judgement about whether it may be applied. It is an input
    # to the Policy Agent, never a substitute for it.
    SKILL_APPLICABLE = "SKILL_APPLICABLE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CheckResult:
    id: str
    title: str
    status: Status
    detail: str
    # Set when the failure means the run must stop before impact analysis rather
    # than merely mark the skill unusable.
    fail_closed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "detail": self.detail,
            "fail_closed": self.fail_closed,
        }


@dataclass
class CheckReport:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    def extend(self, results: list[CheckResult]) -> None:
        self.results.extend(results)

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.status is Status.FAIL]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if r.status is Status.WARN]

    @property
    def fail_closed(self) -> bool:
        return any(r.fail_closed for r in self.failures)

    def verdict(self) -> Verdict:
        if self.failures:
            return Verdict.BLOCKED
        if self.warnings:
            return Verdict.HUMAN_REQUIRED
        return Verdict.SKILL_APPLICABLE

    def exit_code(self) -> int:
        if self.fail_closed:
            return 2
        if self.failures:
            return 1
        return 0

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict().value,
            "exit_code": self.exit_code(),
            "counts": {
                "pass": len([r for r in self.results if r.status is Status.PASS]),
                "warn": len(self.warnings),
                "fail": len(self.failures),
            },
            "results": [r.to_dict() for r in self.results],
        }
