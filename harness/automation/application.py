"""One application interface over ActiveGraph's authoritative EventStore."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from activegraph.core.event import Event
from activegraph.store import EventStore, InMemoryEventStore, SQLiteEventStore

from harness.automation.authoring import (
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
from harness.security import redact_value


class WorkspaceRuntimeActiveError(RuntimeError):
    """Raised when a workspace already has a write-capable runtime."""


@dataclass(frozen=True)
class AutomationDefinition:
    definition_id: str
    name: str
    success_check: str
    action_id: str = "read"
    action_class: str = "R0"
    read_only: bool = True
    actions: tuple[AutomationAction, ...] = ()
    schema_version: str = "v1"


@dataclass(frozen=True)
class ToolResult:
    value: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


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
class RunSummary:
    run_id: str
    definition_id: str
    status: str
    verification_results: tuple[dict[str, Any], ...]
    evidence_references: tuple[EvidenceReference, ...]
    failure_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_value(
            {
                "run_id": self.run_id,
                "definition_id": self.definition_id,
                "status": self.status,
                "verification_results": list(self.verification_results),
                "evidence_references": [asdict(item) for item in self.evidence_references],
                "failure_kind": self.failure_kind,
            }
        )


class ReadOnlyAdapter(Protocol):
    def __call__(self, definition: AutomationDefinition, run_id: str) -> ToolResult: ...


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
    ) -> AutomationProposal:
        budget = budget or ProposalBudget()
        self._validate_budget(budget)
        proposal = model.propose(intent, discovery)
        if not isinstance(proposal, AutomationProposal):
            raise TypeError("Model adapter must return an AutomationProposal")
        return proposal

    def discover_and_propose(
        self,
        intent: AutomationIntent,
        discovery_adapter: DiscoveryAdapter,
        model: ProposalModelAdapter,
        budget: ProposalBudget | None = None,
    ) -> AutomationProposal:
        budget = budget or ProposalBudget()
        self._validate_budget(budget)
        return self.propose(intent, discovery_adapter.discover(intent), model, budget)

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
            definition = AutomationDefinition(
                **{
                    **value["definition"],
                    "actions": tuple(
                        AutomationAction(
                            **{
                                **action,
                                "selector": (
                                    None
                                    if action["selector"] is None
                                    else SelectorEvidence(**action["selector"])
                                ),
                            }
                        )
                        for action in value["definition"]["actions"]
                    ),
                }
            )
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

    def execute_read_only(
        self,
        definition_id: str,
        adapter: ReadOnlyAdapter,
        verify: Callable[[ToolResult], VerificationResult],
    ) -> RunSummary:
        self._require_writer()
        definition = self._definition(definition_id)
        if definition is None:
            raise KeyError(f"Unknown automation definition: {definition_id}")
        if not definition.read_only or definition.action_class != "R0":
            raise ValueError("Only R0 read-only definitions are admitted by this slice")

        run_id = f"run_{uuid4().hex}"
        self._append("rpa.run.started", {"run_id": run_id, "definition_id": definition_id})
        self._append(
            "rpa.action.attempted",
            {"run_id": run_id, "action_id": definition.action_id, "read_only": True},
        )
        try:
            tool_result = adapter(definition, run_id)
            self._append(
                "rpa.action.returned",
                {"run_id": run_id, "value": tool_result.value, "evidence": tool_result.evidence},
            )
            verification = verify(tool_result)
        except Exception as exc:
            tool_result = ToolResult()
            verification = VerificationResult(
                passed=False,
                message="Read-only adapter failed",
                failure_kind="adapter_error",
                evidence={"error": str(exc)},
            )

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
                "rpa.run.completed", {"run_id": run_id, "evidence_id": reference.evidence_id}
            )
        else:
            self._append(
                "rpa.run.failed",
                {
                    "run_id": run_id,
                    "failure_kind": verification.failure_kind or "verification_failed",
                    "evidence_id": reference.evidence_id,
                },
            )
        return self.inspect_run(run_id)

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
        for event in self._store.iter_events():
            if event.type != "rpa.definition.registered":
                continue
            payload = event.payload["definition"]
            if payload["definition_id"] == definition_id:
                return AutomationDefinition(**payload)
        return None

    @staticmethod
    def _validate_definition(definition: AutomationDefinition) -> None:
        if not definition.definition_id or not definition.name or not definition.success_check:
            raise ValueError(
                "Automation definitions require an id, name, and explicit success check"
            )
        if not definition.read_only or definition.action_class != "R0":
            raise ValueError("The first slice accepts only read-only R0 definitions")

    @staticmethod
    def _validate_budget(budget: ProposalBudget) -> None:
        if budget.max_proposals < 1 or budget.max_model_calls < 1:
            raise ValueError("proposal and model-call budgets must permit exactly one proposal")

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
                    state["status"] = "failed"
                    state["failure_kind"] = payload["failure_kind"]
        return state
