"""Typed command/query values shared by CLI, MCP, scheduler, and tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.automation.principals import Principal


@dataclass(frozen=True)
class Command:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    principal: Principal | None = None


@dataclass(frozen=True)
class Query:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    principal: Principal | None = None


@dataclass(frozen=True)
class ApplicationResult:
    ok: bool
    value: Any = None
    error_code: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "value": self.value,
            "error_code": self.error_code,
            "error": self.error,
        }
