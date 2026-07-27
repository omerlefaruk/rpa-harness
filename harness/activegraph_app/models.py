"""Typed contracts returned by the automation-application interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkspaceInfo:
    path: str
    product_version: str
    activegraph_version: str
    pack_name: str
    pack_version: str
    event_schema_version: str
    application_interface_version: str
    event_store_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DefinitionVersionSummary:
    definition_id: str
    version: str
    content_hash: str
    name: str
    action_class: str
    capability: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceReferenceSummary:
    evidence_id: str
    kind: str
    path: str
    redacted: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationSummary:
    verification_id: str
    passed: bool
    failure_kind: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionAttemptSummary:
    attempt_id: str
    capability: str
    status: str
    action_class: str
    verification: VerificationSummary | None = None
    evidence: tuple[EvidenceReferenceSummary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "capability": self.capability,
            "status": self.status,
            "action_class": self.action_class,
            "verification": None if self.verification is None else self.verification.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    definition_id: str
    definition_version: str
    status: str
    failure_kind: str | None = None
    attempts: tuple[ActionAttemptSummary, ...] = field(default_factory=tuple)
    event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "status": self.status,
            "failure_kind": self.failure_kind,
            "attempts": [item.to_dict() for item in self.attempts],
            "event_count": self.event_count,
        }
