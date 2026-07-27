"""Pure data types for the AutomationApplication lifecycle seam.

Lifecycle SoT types live here so application.py stays focused on behavior.
Import from harness.automation.application (re-exports) or this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from harness.automation.authoring import AutomationAction, DiscoveryEvidence
from harness.security import redact_value


class WorkspaceRuntimeActiveError(RuntimeError):
    """Raised when a workspace already has a write-capable runtime."""


class ApprovalError(PermissionError):
    """Raised when an Approval Grant is missing, stale, or scope-mismatched."""

    code = "automation_approval_denied"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class AuthorityError(PermissionError):
    """Raised when action classification or governance gates fail closed."""

    code = "automation_authority_denied"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class DuplicateWriteError(RuntimeError):
    """Raised when a write would violate at-most-once admission."""

    code = "automation_duplicate_write"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class AmbiguousWriteError(RuntimeError):
    """Raised when a write adapter cannot prove applied-or-not-applied."""

    code = "automation_write_unknown"

    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        self.message = message
        self.evidence = dict(evidence or {})
        super().__init__(f"{self.code}: {message}")


class ReconciliationError(RuntimeError):
    """Raised when reconciliation is invalid or still unresolved for unattended work."""

    code = "automation_reconciliation_invalid"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class RepairError(RuntimeError):
    """Raised when a repair trial or promotion is rejected."""

    code = "automation_repair_rejected"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class BudgetExhaustedError(RuntimeError):
    """Raised when a run budget dimension is exhausted."""

    code = "automation_budget_exhausted"

    def __init__(self, message: str, *, budget: str, last_transition: str | None = None) -> None:
        self.message = message
        self.budget = budget
        self.last_transition = last_transition
        super().__init__(f"{self.code}: {message}")


class RepeatedTransitionError(RuntimeError):
    """Raised when an equivalent autonomous transition repeats without state change."""

    code = "automation_repeated_transition"

    def __init__(self, message: str, *, fingerprint: str) -> None:
        self.message = message
        self.fingerprint = fingerprint
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class RunBudget:
    """Separate ceilings for autonomous proposal, tool, action, verification, and repair work."""

    max_model_proposals: int = 3
    max_tool_calls: int = 10
    max_action_attempts: int = 5
    max_verification_attempts: int = 5
    max_repair_trials: int = 2

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


BUDGET_DIMENSIONS = (
    "model_proposals",
    "tool_calls",
    "action_attempts",
    "verification_attempts",
    "repair_trials",
)

TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "failed", "blocked", "needs_reconciliation", "rejected", "cancelled"}
)


@dataclass(frozen=True)
class AutomationDefinition:
    definition_id: str
    name: str
    success_check: str
    action_id: str = "read"
    action_class: str = "R0"
    read_only: bool = True
    actions: tuple[AutomationAction, ...] = ()
    target_scope: str = ""
    record_scope: str = ""
    side_effect_scope: str = ""
    idempotency_scope: str = ""
    credential_names: tuple[str, ...] = ()
    schema_version: str = "v1"


@dataclass(frozen=True)
class ToolResult:
    value: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    # Write adapters set applied|unknown; reads leave None.
    write_outcome: str | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    conclusion: str  # applied | not_applied | still_unknown
    evidence: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    uri: str
    kind: str


@dataclass(frozen=True)
class VerificationResult:
    """Lifecycle verification outcome (AutomationApplication SoT).

    Distinct from harness.verification.contract.CheckResult used by the check-runner.
    """

    passed: bool
    message: str = ""
    failure_kind: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalGrant:
    grant_id: str
    definition_id: str
    definition_version: int
    content_hash: str
    target_scope: str
    record_scope: str
    side_effect_scope: str
    actor: str
    expires_at: str
    action_id: str
    governance_gate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    definition_id: str
    status: str
    verification_results: tuple[dict[str, Any], ...]
    evidence_references: tuple[EvidenceReference, ...]
    failure_kind: str | None = None
    definition_version: int | None = None
    grant_id: str | None = None
    blocked_reason: str | None = None
    exhausted_budget: str | None = None
    last_transition: str | None = None
    next_required: str | None = None
    budget_usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return redact_value(
            {
                "run_id": self.run_id,
                "definition_id": self.definition_id,
                "status": self.status,
                "verification_results": list(self.verification_results),
                "evidence_references": [asdict(item) for item in self.evidence_references],
                "failure_kind": self.failure_kind,
                "definition_version": self.definition_version,
                "grant_id": self.grant_id,
                "blocked_reason": self.blocked_reason,
                "exhausted_budget": self.exhausted_budget,
                "last_transition": self.last_transition,
                "next_required": self.next_required,
                "budget_usage": dict(self.budget_usage),
            }
        )


@dataclass(frozen=True)
class RepairProposal:
    repair_id: str
    parent_definition_id: str
    parent_version: int
    parent_content_hash: str
    failure_run_id: str
    failure_kind: str
    discovery: DiscoveryEvidence
    proposed_definition: AutomationDefinition
    rationale: str = ""
    surface: str = "browser"  # browser | desktop

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_id": self.repair_id,
            "parent_definition_id": self.parent_definition_id,
            "parent_version": self.parent_version,
            "parent_content_hash": self.parent_content_hash,
            "failure_run_id": self.failure_run_id,
            "failure_kind": self.failure_kind,
            "discovery": asdict(self.discovery),
            "proposed_definition": asdict(self.proposed_definition),
            "rationale": self.rationale,
            "surface": self.surface,
        }


@dataclass(frozen=True)
class RepairTrialResult:
    trial_id: str
    repair_id: str
    status: str
    verification: dict[str, Any]
    evidence_references: tuple[EvidenceReference, ...]
    parent_diff: dict[str, Any]
    failure_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "repair_id": self.repair_id,
            "status": self.status,
            "verification": self.verification,
            "evidence_references": [asdict(item) for item in self.evidence_references],
            "parent_diff": self.parent_diff,
            "failure_kind": self.failure_kind,
        }
