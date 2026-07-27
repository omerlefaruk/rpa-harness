"""One application interface over ActiveGraph's authoritative EventStore."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from activegraph.core.event import Event
from activegraph.store import EventStore, InMemoryEventStore, SQLiteEventStore

from harness.automation.authoring import (
    ALLOWED_ACTION_CLASSES,
    WRITE_ACTION_CLASSES,
    AutomationAction,
    AutomationIntent,
    AutomationProposal,
    DefinitionVersion,
    DiscoveryAdapter,
    DiscoveryEvidence,
    ProposalBudget,
    ProposalModelAdapter,
    ProposalValidation,
    ProposalValidationError,
    SelectorEvidence,
    content_hash,
    validate_proposal,
)
from harness.security import SECRET_REF_RE, SecretValue, redact_value


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
class VerificationResult:
    passed: bool
    message: str = ""
    failure_kind: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    uri: str
    kind: str


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


class ReadOnlyAdapter(Protocol):
    def __call__(self, definition: AutomationDefinition, run_id: str) -> ToolResult: ...


class WriteAdapter(Protocol):
    def __call__(
        self,
        definition: AutomationDefinition,
        run_id: str,
        *,
        secrets: Mapping[str, SecretValue],
        action: AutomationAction | None,
    ) -> ToolResult: ...


class SecretAdapter(Protocol):
    def resolve(self, name_or_handle: str) -> SecretValue: ...


class MappingSecretAdapter:
    """Resolves named secrets only at the local execution edge."""

    def __init__(self, secrets: Mapping[str, str]) -> None:
        self._secrets = dict(secrets)

    def resolve(self, name_or_handle: str) -> SecretValue:
        name = name_or_handle
        match = SECRET_REF_RE.fullmatch(name_or_handle)
        if match:
            name = match.group(1)
        if name not in self._secrets:
            raise KeyError(f"Unknown secret handle: {name}")
        return SecretValue(name, self._secrets[name])


class AutomationApplication:
    """Registers, executes, and inspects automation through one event-sourced seam."""

    def __init__(
        self,
        workspace: str | Path | None = None,
        *,
        store: EventStore | None = None,
        read_only: bool = False,
    ) -> None:
        self._workspace = Path(workspace) if workspace is not None else None
        self._read_only = read_only
        self._owns_store = store is None
        self._lock_fd: int | None = None
        if self._workspace is not None:
            if not read_only:
                self._workspace.mkdir(parents=True, exist_ok=True)
                self._acquire_writer_lock()
            elif not self._workspace.exists():
                raise FileNotFoundError(f"Workspace does not exist: {self._workspace}")
        self._store = store or self._open_workspace_store()

    @classmethod
    def initialize_workspace(cls, workspace: str | Path) -> None:
        from harness.automation.workspace_runtime import WorkspaceRuntimeManager

        # Pinned runtime install first; operator dirs are preserved across upgrades.
        WorkspaceRuntimeManager(workspace).initialize()
        app = cls(workspace)
        app.close()

    def close(self) -> None:
        if self._owns_store:
            self._store.close()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
            self._lock_path().unlink(missing_ok=True)

    def register_definition(self, definition: AutomationDefinition) -> None:
        self._require_writer()
        self._validate_definition(definition)
        if self._definition(definition.definition_id) is not None:
            raise ValueError(
                f"Automation definition already registered: {definition.definition_id}"
            )
        self._append("rpa.definition.registered", {"definition": asdict(definition)})

    def propose(
        self,
        intent: AutomationIntent,
        discovery: DiscoveryEvidence,
        model: ProposalModelAdapter,
        budget: ProposalBudget | None = None,
        *,
        run_id: str | None = None,
        run_budget: RunBudget | None = None,
    ) -> AutomationProposal:
        budget = budget or ProposalBudget()
        self._validate_budget(budget)
        if run_id is not None:
            self.admit_transition(
                run_id,
                behavior="model_propose",
                subject=intent.intent_id,
                input_state={
                    "objective": intent.objective,
                    "capabilities": list(intent.required_capabilities),
                    "discovery_id": discovery.evidence_id,
                    "selectors": [asdict(item) for item in discovery.selectors],
                },
                budget_dimension="model_proposals",
                run_budget=run_budget,
            )
        proposal = model.propose(intent, discovery)
        if not isinstance(proposal, AutomationProposal):
            raise TypeError("Model adapter must return an AutomationProposal")
        self._reject_model_authority_escape(proposal)
        return proposal

    def discover_and_propose(
        self,
        intent: AutomationIntent,
        discovery_adapter: DiscoveryAdapter,
        model: ProposalModelAdapter,
        budget: ProposalBudget | None = None,
        *,
        run_id: str | None = None,
        run_budget: RunBudget | None = None,
    ) -> AutomationProposal:
        budget = budget or ProposalBudget()
        self._validate_budget(budget)
        return self.propose(
            intent,
            discovery_adapter.discover(intent),
            model,
            budget,
            run_id=run_id,
            run_budget=run_budget,
        )

    def begin_run(
        self,
        definition_id: str,
        *,
        budget: RunBudget | None = None,
        definition_version: int | None = None,
        grant_id: str | None = None,
        read_only: bool = True,
    ) -> str:
        """Start a run with explicit autonomous budgets for spiral control."""

        self._require_writer()
        definition = self._definition(definition_id)
        if definition is None:
            raise KeyError(f"Unknown automation definition: {definition_id}")
        run_budget = budget or RunBudget()
        self._validate_run_budget(run_budget)
        run_id = f"run_{uuid4().hex}"
        self._append(
            "rpa.run.started",
            {
                "run_id": run_id,
                "definition_id": definition_id,
                "definition_version": definition_version,
                "grant_id": grant_id,
                "read_only": read_only,
                "budget": run_budget.to_dict(),
            },
        )
        return run_id

    def admit_transition(
        self,
        run_id: str,
        *,
        behavior: str,
        subject: str,
        input_state: Mapping[str, Any],
        budget_dimension: str,
        run_budget: RunBudget | None = None,
        state_changed: bool = False,
    ) -> str:
        """Admit one autonomous transition or block on repeat/budget exhaustion."""

        self._require_writer()
        state = self._project_run(run_id)
        if state is None:
            raise KeyError(f"Unknown run: {run_id}")
        if state["status"] in TERMINAL_RUN_STATUSES:
            raise RuntimeError(f"Run {run_id} is already terminal ({state['status']})")
        if budget_dimension not in BUDGET_DIMENSIONS:
            raise ValueError(f"Unknown budget dimension: {budget_dimension}")

        budget = run_budget or self._run_budget(run_id) or RunBudget()
        self._validate_run_budget(budget)
        usage = dict(state.get("budget_usage") or {})
        used = int(usage.get(budget_dimension, 0))
        limit = int(budget.to_dict()[f"max_{budget_dimension}"])
        if used >= limit:
            reason = (
                f"budget exhausted: {budget_dimension} "
                f"(used={used}, max={limit}); last_transition={state.get('last_transition')}"
            )
            self._block_run(
                run_id,
                reason=reason,
                exhausted_budget=budget_dimension,
                last_transition=state.get("last_transition"),
                next_required="human review or external deterministic state change",
            )
            raise BudgetExhaustedError(
                reason,
                budget=budget_dimension,
                last_transition=state.get("last_transition"),
            )

        fingerprint = self.transition_fingerprint(behavior, subject, input_state)
        prior = state.get("transition_fingerprints") or []
        if fingerprint in prior and not state_changed:
            reason = (
                f"repeated transition blocked: behavior={behavior} subject={subject} "
                f"fingerprint={fingerprint}; requires deterministic state change"
            )
            self._block_run(
                run_id,
                reason=reason,
                exhausted_budget=None,
                last_transition=fingerprint,
                next_required="deterministic external or subject state change before retry",
            )
            raise RepeatedTransitionError(reason, fingerprint=fingerprint)

        usage[budget_dimension] = used + 1
        self._append(
            "rpa.transition.admitted",
            {
                "run_id": run_id,
                "behavior": behavior,
                "subject": subject,
                "fingerprint": fingerprint,
                "budget_dimension": budget_dimension,
                "budget_usage": usage,
                "input_state_hash": self._input_state_hash(input_state),
            },
        )
        return fingerprint

    @staticmethod
    def transition_fingerprint(
        behavior: str, subject: str, input_state: Mapping[str, Any]
    ) -> str:
        material = {
            "behavior": behavior,
            "subject": subject,
            "input_state_hash": AutomationApplication._input_state_hash(input_state),
        }
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def poll_until(
        self,
        run_id: str,
        probe: Callable[[], Any],
        *,
        subject: str,
        input_state: Mapping[str, Any] | None = None,
        run_budget: RunBudget | None = None,
        max_polls: int | None = None,
    ) -> Any:
        """Poll with budgets; persistent exceptions surface instead of being swallowed."""

        attempts = 0
        last_error: Exception | None = None
        while True:
            attempts += 1
            if max_polls is not None and attempts > max_polls:
                raise RuntimeError(f"poll limit exceeded for run {run_id}")
            self.admit_transition(
                run_id,
                behavior="poll",
                subject=subject,
                input_state=input_state or {"attempt": attempts},
                budget_dimension="tool_calls",
                run_budget=run_budget,
                state_changed=True,
            )
            try:
                return probe()
            except Exception as exc:  # surface persistent failures after budget pressure
                last_error = exc
                self._append(
                    "rpa.poll.failed",
                    {
                        "run_id": run_id,
                        "subject": subject,
                        "error": str(exc),
                        "attempt": attempts,
                    },
                )
                # Do not swallow: after recording, re-raise so callers cannot ignore.
                raise

    @staticmethod
    def validate_proposal(proposal: AutomationProposal) -> ProposalValidation:
        return validate_proposal(proposal)

    def register_proposal(self, proposal: AutomationProposal) -> DefinitionVersion:
        self._require_writer()
        validation = validate_proposal(proposal)
        if not validation.accepted:
            raise ProposalValidationError(validation.errors)
        versions = self.definition_versions(proposal.definition.definition_id)
        version = DefinitionVersion(
            definition=proposal.definition,
            version=len(versions) + 1,
            content_hash=content_hash(proposal.definition),
            proposal_id=proposal.proposal_id,
        )
        self._append("rpa.definition.version.registered", {"definition_version": asdict(version)})
        return version

    def definition_versions(self, definition_id: str) -> tuple[DefinitionVersion, ...]:
        versions: list[DefinitionVersion] = []
        for event in self._store.iter_events():
            if event.type != "rpa.definition.version.registered":
                continue
            value = event.payload["definition_version"]
            definition = self._definition_from_payload(value["definition"])
            if definition.definition_id == definition_id:
                versions.append(
                    DefinitionVersion(
                        definition=definition,
                        version=value["version"],
                        content_hash=value["content_hash"],
                        proposal_id=value["proposal_id"],
                        schema_version=value.get("schema_version", "v1"),
                    )
                )
        return tuple(versions)

    def grant_approval(
        self,
        *,
        definition_id: str,
        version: int,
        actor: str,
        target_scope: str,
        record_scope: str,
        side_effect_scope: str,
        expires_at: datetime | str,
        action_id: str | None = None,
        governance_gate: bool = False,
    ) -> ApprovalGrant:
        """Record an immutable Approval Grant bound to one Definition Version."""

        self._require_writer()
        definition_version = self._definition_version(definition_id, version)
        if definition_version is None:
            raise KeyError(f"Unknown definition version: {definition_id}@{version}")
        definition = definition_version.definition
        action_class = self._primary_action_class(definition)
        if action_class not in ALLOWED_ACTION_CLASSES:
            raise AuthorityError("missing or invalid action class")
        if action_class == "R4" and not governance_gate:
            raise AuthorityError("R4 requires a governance gate")
        if action_class in WRITE_ACTION_CLASSES and action_class in {"R3", "R4"}:
            if not target_scope or not record_scope or not side_effect_scope:
                raise ApprovalError("write approvals require target, record, and side-effect scopes")
        expiry = expires_at if isinstance(expires_at, str) else expires_at.astimezone(UTC).isoformat()
        grant = ApprovalGrant(
            grant_id=f"grant_{uuid4().hex}",
            definition_id=definition_id,
            definition_version=version,
            content_hash=definition_version.content_hash,
            target_scope=target_scope,
            record_scope=record_scope,
            side_effect_scope=side_effect_scope,
            actor=actor,
            expires_at=expiry,
            action_id=action_id or definition.action_id,
            governance_gate=governance_gate,
        )
        self._append("rpa.approval.granted", {"approval_grant": grant.to_dict()})
        return grant

    def execute_read_only(
        self,
        definition_id: str,
        adapter: ReadOnlyAdapter,
        verify: Callable[[ToolResult], VerificationResult],
        *,
        budget: RunBudget | None = None,
    ) -> RunSummary:
        self._require_writer()
        definition = self._definition(definition_id)
        if definition is None:
            raise KeyError(f"Unknown automation definition: {definition_id}")
        if not definition.read_only or definition.action_class != "R0":
            raise AuthorityError("Only R0 read-only definitions are admitted by execute_read_only")

        run_id = self.begin_run(definition_id, budget=budget, read_only=True)
        self.admit_transition(
            run_id,
            behavior="tool_call",
            subject=definition.action_id,
            input_state={"definition_id": definition_id, "read_only": True},
            budget_dimension="tool_calls",
            run_budget=budget,
        )
        self.admit_transition(
            run_id,
            behavior="action_attempt",
            subject=definition.action_id,
            input_state={"definition_id": definition_id, "read_only": True},
            budget_dimension="action_attempts",
            run_budget=budget,
        )
        self._append(
            "rpa.action.attempted",
            {
                "run_id": run_id,
                "action_id": definition.action_id,
                "read_only": True,
                "action_class": definition.action_class,
                "idempotency_scope": definition.idempotency_scope or definition.action_id,
            },
        )
        try:
            tool_result = adapter(definition, run_id)
            self._append(
                "rpa.action.returned",
                {"run_id": run_id, "value": tool_result.value, "evidence": tool_result.evidence},
            )
            self.admit_transition(
                run_id,
                behavior="verification",
                subject=definition.action_id,
                input_state={
                    "definition_id": definition_id,
                    "value": tool_result.value,
                    "evidence": tool_result.evidence,
                },
                budget_dimension="verification_attempts",
                run_budget=budget,
            )
            verification = verify(tool_result)
        except (BudgetExhaustedError, RepeatedTransitionError):
            raise
        except Exception as exc:
            tool_result = ToolResult()
            verification = VerificationResult(
                passed=False,
                message="Read-only adapter failed",
                failure_kind="adapter_error",
                evidence={"error": str(exc)},
            )

        return self._finalize_run(run_id, tool_result, verification)

    def execute_write(
        self,
        definition_id: str,
        *,
        version: int,
        grant_id: str,
        adapter: WriteAdapter,
        verify: Callable[[ToolResult], VerificationResult],
        actor: str,
        secret_adapter: SecretAdapter | None = None,
        target_scope: str | None = None,
        record_scope: str | None = None,
        side_effect_scope: str | None = None,
        now: datetime | None = None,
    ) -> RunSummary:
        """Execute one approval-gated write with at-most-once admission and verification."""

        self._require_writer()
        definition_version = self._definition_version(definition_id, version)
        if definition_version is None:
            raise KeyError(f"Unknown definition version: {definition_id}@{version}")
        definition = definition_version.definition
        action_class = self._primary_action_class(definition)
        if action_class not in ALLOWED_ACTION_CLASSES:
            raise AuthorityError("missing or invalid action class")
        if definition.read_only or action_class not in WRITE_ACTION_CLASSES:
            raise AuthorityError("execute_write admits only write-capable action classes")
        if action_class in {"R3", "R4"}:
            grant = self._require_matching_grant(
                grant_id=grant_id,
                definition_version=definition_version,
                actor=actor,
                action_id=definition.action_id,
                target_scope=target_scope or definition.target_scope,
                record_scope=record_scope or definition.record_scope,
                side_effect_scope=side_effect_scope or definition.side_effect_scope,
                action_class=action_class,
                now=now or datetime.now(UTC),
            )
        else:
            # R1/R2 may run under automatic authority when scopes match the definition.
            grant = self._approval_grant(grant_id)
            if grant is not None:
                grant = self._require_matching_grant(
                    grant_id=grant_id,
                    definition_version=definition_version,
                    actor=actor,
                    action_id=definition.action_id,
                    target_scope=target_scope or definition.target_scope,
                    record_scope=record_scope or definition.record_scope,
                    side_effect_scope=side_effect_scope or definition.side_effect_scope,
                    action_class=action_class,
                    now=now or datetime.now(UTC),
                )
            else:
                raise ApprovalError("approval grant is required for write execution")

        action = self._primary_action(definition)
        idempotency_scope = (
            definition.idempotency_scope
            or f"{definition.definition_id}:{version}:{definition.action_id}:{grant.record_scope}"
        )
        if self._write_already_admitted(definition.action_id, idempotency_scope):
            raise DuplicateWriteError(
                "write already admitted for run/action/idempotency scope"
            )

        run_id = f"run_{uuid4().hex}"
        self._append(
            "rpa.run.started",
            {
                "run_id": run_id,
                "definition_id": definition_id,
                "definition_version": version,
                "content_hash": definition_version.content_hash,
                "grant_id": grant.grant_id,
                "read_only": False,
                "action_class": action_class,
            },
        )
        # Action Attempt must be accepted before external I/O begins.
        self._append(
            "rpa.action.attempted",
            {
                "run_id": run_id,
                "action_id": definition.action_id,
                "read_only": False,
                "action_class": action_class,
                "idempotency_scope": idempotency_scope,
                "grant_id": grant.grant_id,
            },
        )
        secrets = self._resolve_secrets(definition, action, secret_adapter)
        try:
            tool_result = adapter(definition, run_id, secrets=secrets, action=action)
        except AmbiguousWriteError as exc:
            tool_result = ToolResult(
                evidence=dict(exc.evidence),
                write_outcome="unknown",
            )
        except Exception as exc:
            tool_result = ToolResult(
                evidence={"error": str(exc)},
                write_outcome="unknown"
                if self._looks_like_transport_or_timeout(exc)
                else "failed",
            )
            if tool_result.write_outcome != "unknown":
                verification = VerificationResult(
                    passed=False,
                    message="Write adapter failed",
                    failure_kind="adapter_error",
                    evidence={"error": str(exc)},
                )
                return self._finalize_run(
                    run_id,
                    tool_result,
                    verification,
                    definition_version=version,
                    grant_id=grant.grant_id,
                )

        outcome = tool_result.write_outcome or "applied"
        if outcome == "unknown":
            return self._mark_needs_reconciliation(
                run_id,
                tool_result,
                definition_version=version,
                grant_id=grant.grant_id,
                action_id=definition.action_id,
                idempotency_scope=idempotency_scope,
                reason="write outcome unknown; applied-or-not-applied not proven",
            )

        self._append(
            "rpa.action.returned",
            {
                "run_id": run_id,
                "value": tool_result.value,
                "evidence": tool_result.evidence,
                "applied": True,
                "write_outcome": outcome,
            },
        )
        verification = verify(tool_result)
        return self._finalize_run(
            run_id,
            tool_result,
            verification,
            definition_version=version,
            grant_id=grant.grant_id,
        )

    def reconcile(
        self,
        run_id: str,
        *,
        read_probe: Callable[[], ToolResult],
        conclude: Callable[[ToolResult], ReconciliationResult],
        verify: Callable[[ToolResult], VerificationResult] | None = None,
    ) -> RunSummary:
        """Resolve an ambiguous write using only read-only evidence."""

        self._require_writer()
        state = self._project_run(run_id)
        if state is None:
            raise KeyError(f"Unknown run: {run_id}")
        if state["status"] != "needs_reconciliation":
            raise ReconciliationError("run is not waiting for reconciliation")

        try:
            observed = read_probe()
        except Exception as exc:
            observed = ToolResult(evidence={"error": str(exc)}, write_outcome="unknown")
        if not isinstance(observed, ToolResult):
            raise TypeError("reconciliation read probe must return ToolResult")

        result = conclude(observed)
        if not isinstance(result, ReconciliationResult):
            raise TypeError("conclude must return ReconciliationResult")
        if result.conclusion not in {"applied", "not_applied", "still_unknown"}:
            raise ReconciliationError("invalid reconciliation conclusion")

        self._append(
            "rpa.reconciliation.recorded",
            {
                "run_id": run_id,
                "conclusion": result.conclusion,
                "message": result.message,
                "evidence": result.evidence,
                "action_id": state.get("action_id"),
                "idempotency_scope": state.get("idempotency_scope"),
            },
        )
        reference = self._record_evidence(
            run_id,
            observed,
            VerificationResult(
                passed=result.conclusion == "applied",
                message=result.message or result.conclusion,
                failure_kind=None
                if result.conclusion == "applied"
                else "needs_reconciliation",
                evidence=result.evidence,
            ),
        )

        if result.conclusion == "still_unknown":
            self._append(
                "rpa.run.failed",
                {
                    "run_id": run_id,
                    "failure_kind": "still_unknown",
                    "evidence_id": reference.evidence_id,
                    "status": "needs_reconciliation",
                },
            )
            # Remain terminal for unattended execution.
            self._append(
                "rpa.run.needs_reconciliation",
                {
                    "run_id": run_id,
                    "reason": "reconciliation still unknown",
                    "terminal": True,
                    "evidence_id": reference.evidence_id,
                },
            )
            return self.inspect_run(run_id)

        if result.conclusion == "not_applied":
            self._append(
                "rpa.reconciliation.not_applied",
                {
                    "run_id": run_id,
                    "action_id": state.get("action_id"),
                    "idempotency_scope": state.get("idempotency_scope"),
                    "authorizes_retry": True,
                    "evidence_id": reference.evidence_id,
                },
            )
            self._append(
                "rpa.run.failed",
                {
                    "run_id": run_id,
                    "failure_kind": "not_applied",
                    "evidence_id": reference.evidence_id,
                },
            )
            return self.inspect_run(run_id)

        # Applied: proceed to verification without another write.
        if verify is None:
            raise ReconciliationError("applied reconciliation requires verify callback")
        synthetic = ToolResult(
            value=observed.value or {"reconciled": "applied"},
            evidence={**observed.evidence, **result.evidence},
            write_outcome="applied",
        )
        verification = verify(synthetic)
        return self._finalize_run(
            run_id,
            synthetic,
            verification,
            definition_version=state.get("definition_version"),
            grant_id=state.get("grant_id"),
        )

    def inspect_run(self, run_id: str) -> RunSummary:
        state = self._project_run(run_id)
        if state is None:
            raise KeyError(f"Unknown run: {run_id}")
        return RunSummary(
            run_id=run_id,
            definition_id=state["definition_id"],
            status=state["status"],
            verification_results=tuple(state["verifications"]),
            evidence_references=tuple(state["evidence"]),
            failure_kind=state["failure_kind"],
            definition_version=state.get("definition_version"),
            grant_id=state.get("grant_id"),
            blocked_reason=state.get("blocked_reason"),
            exhausted_budget=state.get("exhausted_budget"),
            last_transition=state.get("last_transition"),
            next_required=state.get("next_required"),
            budget_usage=dict(state.get("budget_usage") or {}),
        )

    def _open_workspace_store(self) -> EventStore:
        if self._workspace is None:
            return InMemoryEventStore(run_id="rpa_workspace")
        db_path = self._workspace / "data" / "automation-events.sqlite"
        if not self._read_only:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteEventStore(str(db_path), run_id="rpa_workspace")

    def _acquire_writer_lock(self) -> None:
        lock_path = self._lock_path()
        try:
            self._lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise WorkspaceRuntimeActiveError(
                f"A write-capable automation runtime is already active for {self._workspace}"
            ) from exc

    def _lock_path(self) -> Path:
        assert self._workspace is not None
        return self._workspace / ".automation-runtime.lock"

    def _require_writer(self) -> None:
        if self._read_only:
            raise PermissionError("Read-only automation inspection cannot append lifecycle events")

    def _append(self, event_type: str, payload: dict[str, Any]) -> str:
        event_id = f"evt_{uuid4().hex}"
        self._store.append(
            Event(
                id=event_id,
                type=event_type,
                payload=redact_value(payload),
                timestamp=datetime.now(UTC).isoformat(),
            )
        )
        return event_id

    def _definition(self, definition_id: str) -> AutomationDefinition | None:
        for version in reversed(self.definition_versions(definition_id)):
            return version.definition
        for event in self._store.iter_events():
            if event.type != "rpa.definition.registered":
                continue
            payload = event.payload["definition"]
            if payload["definition_id"] == definition_id:
                return self._definition_from_payload(payload)
        return None

    def _definition_version(self, definition_id: str, version: int) -> DefinitionVersion | None:
        for item in self.definition_versions(definition_id):
            if item.version == version:
                return item
        return None

    def _approval_grant(self, grant_id: str) -> ApprovalGrant | None:
        for event in self._store.iter_events():
            if event.type != "rpa.approval.granted":
                continue
            payload = event.payload["approval_grant"]
            if payload["grant_id"] == grant_id:
                return ApprovalGrant(**payload)
        return None

    def _require_matching_grant(
        self,
        *,
        grant_id: str,
        definition_version: DefinitionVersion,
        actor: str,
        action_id: str,
        target_scope: str,
        record_scope: str,
        side_effect_scope: str,
        action_class: str,
        now: datetime,
    ) -> ApprovalGrant:
        grant = self._approval_grant(grant_id)
        if grant is None:
            raise ApprovalError("approval grant not found")
        if grant.definition_id != definition_version.definition.definition_id:
            raise ApprovalError("approval grant definition mismatch")
        if grant.definition_version != definition_version.version:
            raise ApprovalError("approval grant version mismatch")
        if grant.content_hash != definition_version.content_hash:
            raise ApprovalError("approval grant content hash mismatch")
        if grant.actor != actor:
            raise ApprovalError("approval grant actor mismatch")
        if grant.action_id != action_id:
            raise ApprovalError("approval grant action mismatch")
        if grant.target_scope != target_scope:
            raise ApprovalError("approval grant target scope mismatch")
        if grant.record_scope != record_scope:
            raise ApprovalError("approval grant record scope mismatch")
        if grant.side_effect_scope != side_effect_scope:
            raise ApprovalError("approval grant side-effect scope mismatch")
        expires_at = datetime.fromisoformat(grant.expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now >= expires_at:
            raise ApprovalError("approval grant expired")
        if action_class == "R4" and not grant.governance_gate:
            raise AuthorityError("R4 requires a governance gate")
        return grant

    def _write_already_admitted(self, action_id: str, idempotency_scope: str) -> bool:
        """True when a write is still admitted and not cleared by not_applied reconciliation."""

        admitted = False
        for event in self._store.iter_events():
            payload = event.payload
            if event.type == "rpa.action.attempted":
                if payload.get("read_only"):
                    continue
                if (
                    payload.get("action_id") == action_id
                    and payload.get("idempotency_scope") == idempotency_scope
                ):
                    admitted = True
            elif event.type == "rpa.reconciliation.not_applied":
                if (
                    payload.get("action_id") == action_id
                    and payload.get("idempotency_scope") == idempotency_scope
                    and payload.get("authorizes_retry")
                ):
                    admitted = False
        return admitted

    def _mark_needs_reconciliation(
        self,
        run_id: str,
        tool_result: ToolResult,
        *,
        definition_version: int | None,
        grant_id: str | None,
        action_id: str,
        idempotency_scope: str,
        reason: str,
    ) -> RunSummary:
        self._append(
            "rpa.action.returned",
            {
                "run_id": run_id,
                "value": tool_result.value,
                "evidence": tool_result.evidence,
                "applied": None,
                "write_outcome": "unknown",
            },
        )
        reference = self._record_evidence(
            run_id,
            tool_result,
            VerificationResult(
                passed=False,
                message=reason,
                failure_kind="needs_reconciliation",
                evidence=tool_result.evidence,
            ),
        )
        self._append(
            "rpa.run.needs_reconciliation",
            {
                "run_id": run_id,
                "reason": reason,
                "evidence_id": reference.evidence_id,
                "definition_version": definition_version,
                "grant_id": grant_id,
                "action_id": action_id,
                "idempotency_scope": idempotency_scope,
                "terminal": False,
            },
        )
        return self.inspect_run(run_id)

    @staticmethod
    def _looks_like_transport_or_timeout(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".lower()
        markers = (
            "timeout",
            "timed out",
            "transport",
            "connection reset",
            "connection aborted",
            "broken pipe",
            "process interrupted",
            "malformed",
            "incomplete response",
        )
        return any(marker in text for marker in markers)

    def _resolve_secrets(
        self,
        definition: AutomationDefinition,
        action: AutomationAction | None,
        secret_adapter: SecretAdapter | None,
    ) -> dict[str, SecretValue]:
        names = list(definition.credential_names)
        if action is not None:
            names.extend(action.credential_names)
            for value in action.inputs.values():
                if isinstance(value, str):
                    match = SECRET_REF_RE.fullmatch(value)
                    if match:
                        names.append(match.group(1))
        unique = tuple(dict.fromkeys(names))
        if not unique:
            return {}
        if secret_adapter is None:
            raise AuthorityError("secret adapter is required for credential-backed writes")
        resolved: dict[str, SecretValue] = {}
        for name in unique:
            secret = secret_adapter.resolve(name)
            if not isinstance(secret, SecretValue):
                raise AuthorityError("secret adapter must return SecretValue handles")
            # Agent-facing surfaces never receive plaintext; only the edge keeps SecretValue.
            resolved[name] = secret
        return resolved

    def _finalize_run(
        self,
        run_id: str,
        tool_result: ToolResult,
        verification: VerificationResult,
        *,
        definition_version: int | None = None,
        grant_id: str | None = None,
    ) -> RunSummary:
        self._append(
            "rpa.verification.recorded",
            {
                "run_id": run_id,
                "passed": verification.passed,
                "message": verification.message,
                "failure_kind": verification.failure_kind,
                "evidence": verification.evidence,
            },
        )
        reference = self._record_evidence(run_id, tool_result, verification)
        if verification.passed:
            self._append(
                "rpa.run.completed",
                {
                    "run_id": run_id,
                    "evidence_id": reference.evidence_id,
                    "definition_version": definition_version,
                    "grant_id": grant_id,
                },
            )
        else:
            self._append(
                "rpa.run.failed",
                {
                    "run_id": run_id,
                    "failure_kind": verification.failure_kind or "verification_failed",
                    "evidence_id": reference.evidence_id,
                    "definition_version": definition_version,
                    "grant_id": grant_id,
                },
            )
        return self.inspect_run(run_id)

    @staticmethod
    def _primary_action(definition: AutomationDefinition) -> AutomationAction | None:
        for action in definition.actions:
            if action.action_id == definition.action_id:
                return action
        return definition.actions[0] if definition.actions else None

    @staticmethod
    def _primary_action_class(definition: AutomationDefinition) -> str:
        action = None
        for item in definition.actions:
            if item.action_id == definition.action_id:
                action = item
                break
        if action is None and definition.actions:
            action = definition.actions[0]
        if action is not None:
            if not action.action_class:
                raise AuthorityError("missing or invalid action class")
            return action.action_class
        if not definition.action_class:
            raise AuthorityError("missing or invalid action class")
        return definition.action_class

    @staticmethod
    def _definition_from_payload(payload: Mapping[str, Any]) -> AutomationDefinition:
        value = dict(payload)
        actions = value.get("actions", ())
        value["actions"] = tuple(
            action
            if isinstance(action, AutomationAction)
            else AutomationAction(
                **{
                    **action,
                    "selector": (
                        None
                        if action.get("selector") is None
                        else SelectorEvidence(**action["selector"])
                    ),
                    "credential_names": tuple(action.get("credential_names", ())),
                    "inputs": dict(action.get("inputs", {})),
                }
            )
            for action in actions
        )
        value["credential_names"] = tuple(value.get("credential_names", ()))
        return AutomationDefinition(**value)

    @staticmethod
    def _validate_definition(definition: AutomationDefinition) -> None:
        if not definition.definition_id or not definition.name or not definition.success_check:
            raise ValueError(
                "Automation definitions require an id, name, and explicit success check"
            )
        if definition.action_class not in ALLOWED_ACTION_CLASSES:
            raise AuthorityError("missing or invalid action class")
        if definition.read_only != (definition.action_class == "R0"):
            raise AuthorityError("missing or invalid action class")
        for action in definition.actions:
            if action.action_class not in ALLOWED_ACTION_CLASSES:
                raise AuthorityError("missing or invalid action class")

    @staticmethod
    def _validate_budget(budget: ProposalBudget) -> None:
        if budget.max_proposals < 1 or budget.max_model_calls < 1:
            raise ValueError("proposal and model-call budgets must permit exactly one proposal")

    @staticmethod
    def _validate_run_budget(budget: RunBudget) -> None:
        values = budget.to_dict()
        for key, value in values.items():
            if int(value) < 1:
                raise ValueError(f"run budget {key} must be at least 1")

    @staticmethod
    def _input_state_hash(input_state: Mapping[str, Any]) -> str:
        canonical = json.dumps(input_state, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _run_budget(self, run_id: str) -> RunBudget | None:
        for event in self._store.iter_events():
            if event.type == "rpa.run.started" and event.payload.get("run_id") == run_id:
                raw = event.payload.get("budget")
                if raw:
                    return RunBudget(**raw)
        return None

    def _block_run(
        self,
        run_id: str,
        *,
        reason: str,
        exhausted_budget: str | None,
        last_transition: str | None,
        next_required: str,
    ) -> None:
        self._append(
            "rpa.run.blocked",
            {
                "run_id": run_id,
                "reason": reason,
                "failure_kind": "budget_or_spiral",
                "exhausted_budget": exhausted_budget,
                "last_transition": last_transition,
                "next_required": next_required,
            },
        )

    @staticmethod
    def _reject_model_authority_escape(proposal: AutomationProposal) -> None:
        """Models cannot raise budgets, change allowlists, retry policy, or force success."""

        forbidden = (
            "budget",
            "budgets",
            "tool_allowlist",
            "allowlist",
            "retry",
            "retries",
            "force_success",
            "mark_successful",
        )
        blob = json.dumps(asdict(proposal), sort_keys=True, default=str).lower()
        for key in forbidden:
            if f'"{key}"' in blob or f"'{key}'" in blob:
                # Only reject when present as model-controlled metadata keys on inputs.
                pass
        for action in getattr(proposal.definition, "actions", ()) or ():
            for key in action.inputs:
                lowered = str(key).lower()
                if lowered in forbidden or lowered.startswith("max_"):
                    raise AuthorityError(
                        "models cannot increase budgets, alter allowlists, invoke retries, "
                        "or mark work successful"
                    )

    def _record_evidence(
        self,
        run_id: str,
        tool_result: ToolResult,
        verification: VerificationResult,
    ) -> EvidenceReference:
        evidence_id = f"evidence_{uuid4().hex}"
        uri = f"evidence/{run_id}.json"
        reference = EvidenceReference(evidence_id=evidence_id, uri=uri, kind="verification")
        self._append(
            "rpa.evidence.referenced",
            {"run_id": run_id, "evidence": asdict(reference)},
        )
        if self._workspace is not None:
            path = self._workspace / uri
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    redact_value(
                        {
                            "run_id": run_id,
                            "tool_evidence": tool_result.evidence,
                            "verification_evidence": verification.evidence,
                        }
                    ),
                    indent=2,
                ),
                encoding="utf-8",
            )
        return reference

    def _project_run(self, run_id: str) -> dict[str, Any] | None:
        state: dict[str, Any] | None = None
        for event in self._store.iter_events():
            payload = event.payload
            if event.type == "rpa.run.started" and payload["run_id"] == run_id:
                state = {
                    "definition_id": payload["definition_id"],
                    "status": "running",
                    "verifications": [],
                    "evidence": [],
                    "failure_kind": None,
                    "definition_version": payload.get("definition_version"),
                    "grant_id": payload.get("grant_id"),
                    "blocked_reason": None,
                    "exhausted_budget": None,
                    "last_transition": None,
                    "next_required": None,
                    "budget_usage": {},
                    "transition_fingerprints": [],
                    "action_id": None,
                    "idempotency_scope": None,
                    "reconciliation": None,
                }
            elif state is not None and payload.get("run_id") == run_id:
                if event.type == "rpa.verification.recorded":
                    state["verifications"].append(
                        {
                            "passed": payload["passed"],
                            "message": payload["message"],
                            "failure_kind": payload["failure_kind"],
                        }
                    )
                elif event.type == "rpa.evidence.referenced":
                    state["evidence"].append(EvidenceReference(**payload["evidence"]))
                elif event.type == "rpa.run.completed":
                    state["status"] = "completed"
                elif event.type == "rpa.run.failed":
                    # still_unknown keeps needs_reconciliation terminal semantics via later event
                    if payload.get("failure_kind") != "still_unknown":
                        state["status"] = "failed"
                    state["failure_kind"] = payload["failure_kind"]
                elif event.type == "rpa.run.blocked":
                    state["status"] = "blocked"
                    state["blocked_reason"] = payload.get("reason")
                    state["failure_kind"] = payload.get("failure_kind")
                    state["exhausted_budget"] = payload.get("exhausted_budget")
                    state["last_transition"] = payload.get("last_transition")
                    state["next_required"] = payload.get("next_required")
                elif event.type == "rpa.run.needs_reconciliation":
                    state["status"] = "needs_reconciliation"
                    state["failure_kind"] = "needs_reconciliation"
                    state["blocked_reason"] = payload.get("reason")
                    state["action_id"] = payload.get("action_id") or state.get("action_id")
                    state["idempotency_scope"] = payload.get("idempotency_scope") or state.get(
                        "idempotency_scope"
                    )
                    if payload.get("terminal"):
                        state["next_required"] = "human inspection; unattended execution stopped"
                elif event.type == "rpa.action.attempted":
                    state["action_id"] = payload.get("action_id")
                    state["idempotency_scope"] = payload.get("idempotency_scope")
                elif event.type == "rpa.reconciliation.recorded":
                    state["reconciliation"] = payload.get("conclusion")
                elif event.type == "rpa.transition.admitted":
                    state["budget_usage"] = dict(payload.get("budget_usage") or {})
                    state["last_transition"] = payload.get("fingerprint")
                    fingerprints = list(state.get("transition_fingerprints") or [])
                    fingerprints.append(payload["fingerprint"])
                    state["transition_fingerprints"] = fingerprints
        return state
