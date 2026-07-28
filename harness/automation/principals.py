"""Explicit caller principals for the application and transport seams."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


PrincipalKind = Literal["agent", "operator", "scheduler", "system"]


class PrincipalError(PermissionError):
    code = "automation_principal_denied"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, kept separate from the business actor."""

    kind: PrincipalKind
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.kind not in {"agent", "operator", "scheduler", "system"}:
            raise ValueError(f"unsupported principal kind: {self.kind}")
        if not self.subject.strip():
            raise ValueError("principal subject must not be empty")

    @property
    def is_agent(self) -> bool:
        return self.kind == "agent"

    @property
    def is_operator(self) -> bool:
        return self.kind in {"operator", "system"}

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "scopes": sorted(self.scopes),
        }


OPERATOR = Principal("operator", "local-operator")
SYSTEM = Principal("system", "application")


def coerce_principal(value: Principal | str | None, *, default: Principal = OPERATOR) -> Principal:
    if value is None:
        return default
    if isinstance(value, Principal):
        return value
    if value in {"agent", "operator", "scheduler", "system"}:
        return Principal(value, f"local-{value}")  # type: ignore[arg-type]
    return Principal("operator", str(value))


def require_operator(principal: Principal | str | None, operation: str) -> Principal:
    resolved = coerce_principal(principal)
    if not resolved.is_operator:
        raise PrincipalError(f"{operation} requires an operator principal")
    return resolved
