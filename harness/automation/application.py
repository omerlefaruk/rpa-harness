"""One application interface over ActiveGraph's authoritative EventStore.

Public lifecycle methods on AutomationApplication:

- register_definition / definition_versions
- propose / discover_and_propose
- begin_run / admit_transition / poll_until
- grant_approval
- execute_read_only / execute_write
- inspect_run
- reconcile
- propose_repair / trial_repair / promote_repair / reject_repair

Pure data types live in harness.automation.models and are re-exported here for
stable import paths (``from harness.automation.application import RunSummary``).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from activegraph import Graph, Runtime
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
from harness.automation.interface import ApplicationResult, Command, Query
from harness.automation.models import (
    BUDGET_DIMENSIONS,
    TERMINAL_RUN_STATUSES,
    AmbiguousWriteError,
    ApprovalError,
    ApprovalGrant,
    AuthorityError,
    AutomationDefinition,
    BudgetExhaustedError,
    DuplicateWriteError,
    EvidenceReference,
    ReconciliationError,
    ReconciliationResult,
    RepairError,
    RepairProposal,
    RepairTrialResult,
    RepeatedTransitionError,
    ReplayDivergenceError,
    RunBudget,
    RunSummary,
    ToolResult,
    VerificationResult,
    WorkspaceRuntimeActiveError,
)
from harness.automation.principals import (
    Principal,
    PrincipalError,
    coerce_principal,
    require_operator,
)
from harness.automation.source_validation import (
    SourceValidation,
    SourceValidationError,
    revision_identity,
    validate_source,
)
from harness.automation.worker import (
    WorkerRequest,
    WorkerResponse,
    decode_response,
    encode_request,
)
from harness.security import SECRET_REF_RE, SecretValue, redact_value

# Re-export pure types for existing ``from harness.automation.application import X`` call sites.
__all__ = [
    "AmbiguousWriteError",
    "ApprovalError",
    "ApprovalGrant",
    "AuthorityError",
    "AutomationApplication",
    "AutomationDefinition",
    "BUDGET_DIMENSIONS",
    "BudgetExhaustedError",
    "DuplicateWriteError",
    "EvidenceReference",
    "MappingSecretAdapter",
    "ApplicationResult",
    "Command",
    "Query",
    "Principal",
    "PrincipalError",
    "ReplayDivergenceError",
    "SourceValidation",
    "SourceValidationError",
    "ReadOnlyAdapter",
    "ReconciliationError",
    "ReconciliationResult",
    "RepairError",
    "RepairProposal",
    "RepairTrialResult",
    "RepeatedTransitionError",
    "RunBudget",
    "RunSummary",
    "SecretAdapter",
    "TERMINAL_RUN_STATUSES",
    "ToolResult",
    "VerificationResult",
    "WriteAdapter",
    "WorkspaceRuntimeActiveError",
]

BROWSER_SELECTOR_PRIORITY = ("role", "label", "test_id", "css", "xpath", "coordinate")
DESKTOP_SELECTOR_PRIORITY = (
    "automation_id",
    "name",
    "class",
    "tree_path",
    "image",
    "coordinate",
)
WEAK_REPAIR_STRATEGIES = frozenset({"css", "xpath", "coordinate", "image"})


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
        self._store = store if store is not None else self._open_workspace_store()
        # ActiveGraph owns the durable event stream and materialized graph. The
        # application keeps its public compatibility projection, but never
        # writes directly to the backend after this point.
        self._graph = Graph(run_id=self._store.run_id)
        existing_events = list(self._store.iter_events())
        for event in existing_events:
            self._graph._replay_event(event)  # noqa: SLF001 - load boundary
        self._graph.ids.reseed_from_events(existing_events)
        from harness.automation.pack import pack

        pack_already_loaded = any(event.type == "pack.loaded" for event in self._graph.events)
        if pack_already_loaded:
            # Rebuild pack validators without persisting a duplicate loader
            # event (the loader's first event id is deterministic).
            self._runtime = Runtime(self._graph)
            self._runtime.load_pack(pack)
            self._graph.attach_store(self._store)
        else:
            self._runtime = Runtime(self._graph, store=self._store)
            self._runtime.load_pack(pack)
        if not self._graph.objects(type="workspace"):
            self._graph.add_object(
                "workspace",
                {"workspace_id": self._store.run_id, "status": "active", "schema_version": "1"},
                actor="system",
            )

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

    @property
    def graph(self) -> Graph:
        """Read-only access to the canonical ActiveGraph projection."""

        return self._graph

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    def execute_command(
        self,
        command: Command | str,
        payload: Mapping[str, Any] | None = None,
        *,
        principal: Principal | str | None = None,
    ) -> ApplicationResult:
        """Run a catalog command through the same seam as every transport."""

        if isinstance(command, Command):
            name, values, caller = command.name, dict(command.payload), command.principal
        else:
            name, values, caller = command, dict(payload or {}), principal
        caller = coerce_principal(caller)
        try:
            if name == "list_feature_skills":
                from harness.automation.skills import discover_skills

                return ApplicationResult(True, [skill.to_dict() for skill in discover_skills()])
            if name == "validate_source":
                return ApplicationResult(
                    True,
                    self.validate_source(
                        str(values.get("source", "")),
                        dependency_lock=str(values.get("dependency_lock", "")),
                        skill_hashes=tuple(values.get("skill_hashes", ())),
                        declared_action_class=str(values.get("action_class", "R0")),
                    ).to_dict(),
                )
            if name == "request_approval":
                self._require_writer()
                self._append(
                    "rpa.approval.requested",
                    {"request": values, "principal": caller.to_dict()},
                )
                return ApplicationResult(
                    True, {"requested": True, "operator_review_required": True}
                )
            if name == "workspace_status":
                return ApplicationResult(True, self.graph_status())
            if name == "register_definition":
                self.register_definition(values["definition"], principal=caller)
                return ApplicationResult(
                    True, {"definition_id": values["definition"].definition_id}
                )
            if name == "inspect_run":
                return ApplicationResult(
                    True, self.inspect_run(str(values["run_id"]).strip()).to_dict()
                )
            if name == "grant_approval":
                return ApplicationResult(
                    True, self.grant_approval(principal=caller, **values).to_dict()
                )
            raise ValueError(f"unknown application command: {name}")
        except Exception as exc:
            return ApplicationResult(
                False,
                error_code=getattr(exc, "code", "automation_operation_failed"),
                error=str(exc),
            )

    command = execute_command

    def execute_query(
        self,
        query: Query | str,
        payload: Mapping[str, Any] | None = None,
        *,
        principal: Principal | str | None = None,
    ) -> ApplicationResult:
        if isinstance(query, Query):
            name, values = query.name, dict(query.payload)
        else:
            name, values = query, dict(payload or {})
        try:
            if name == "workspace_status":
                return ApplicationResult(True, self.graph_status())
            if name == "automations":
                return ApplicationResult(True, self.graph_automations())
            if name == "revisions":
                return ApplicationResult(True, self.graph_revisions(values.get("definition_id")))
            if name == "inspect_run":
                return ApplicationResult(True, self.inspect_run(str(values["run_id"])).to_dict())
            raise ValueError(f"unknown application query: {name}")
        except Exception as exc:
            return ApplicationResult(
                False,
                error_code=getattr(exc, "code", "automation_operation_failed"),
                error=str(exc),
            )

    query = execute_query

    def graph_status(self) -> dict[str, Any]:
        return {
            "run_id": self._graph.run_id,
            "objects": len(self._graph.all_objects()),
            "relations": len(self._graph.all_relations()),
            "events": len(self._graph.events),
            "workspace": next((o.data for o in self._graph.objects(type="workspace")), None),
        }

    def graph_automations(self) -> list[dict[str, Any]]:
        return [dict(obj.data) for obj in self._graph.objects(type="automation")]

    def graph_revisions(self, definition_id: str | None = None) -> list[dict[str, Any]]:
        values = [dict(obj.data) for obj in self._graph.objects(type="automation_revision")]
        if definition_id is not None:
            values = [value for value in values if value.get("definition_id") == definition_id]
        return values

    def _fork_canonical(self, label: str) -> tuple[str | None, Runtime | None]:
        """Create a real ActiveGraph child when the workspace is SQLite-backed."""

        if not isinstance(self._store, SQLiteEventStore):
            return None, None
        events = list(self._store.iter_events())
        if not events:
            return None, None
        try:
            child = self._runtime.fork(events[-1].id, label=label)
        except Exception:
            return None, None
        return child.run_id, child

    def _load_fork(self, run_id: str) -> Runtime | None:
        if not isinstance(self._store, SQLiteEventStore):
            return None
        try:
            return Runtime.load(self._store.path, run_id=run_id)
        except Exception:
            return None

    def register_definition(
        self,
        definition: AutomationDefinition,
        *,
        principal: Principal | str | None = None,
    ) -> None:
        self._require_writer()
        caller = coerce_principal(principal)
        self._validate_definition(definition)
        if self._definition(definition.definition_id) is not None:
            raise ValueError(
                f"Automation definition already registered: {definition.definition_id}"
            )
        self._append("rpa.definition.registered", {"definition": asdict(definition)})
        automation = self._graph.add_object(
            "automation",
            {
                "definition_id": definition.definition_id,
                "name": definition.name,
                "action_class": definition.action_class,
                "read_only": definition.read_only,
                "status": "registered",
            },
            actor=caller.subject,
        )
        revision = self._graph.add_object(
            "automation_revision",
            {
                "definition_id": definition.definition_id,
                "version": 0,
                "content_hash": content_hash(definition),
                "source_hash": definition.source_hash,
                "immutable": True,
                "action_manifest": asdict(definition.action_manifest)
                if definition.action_manifest
                else {},
            },
            actor=caller.subject,
        )
        self._graph.add_relation(automation.id, revision.id, "has_revision", actor=caller.subject)

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
        self._graph.add_object(
            "workflow_run",
            {
                "run_id": run_id,
                "definition_id": definition_id,
                "status": "running",
                "parent_run_id": self._graph.run_id,
                "fork_point": self._graph.events[-1].id if self._graph.events else "",
            },
            actor="system",
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
    def transition_fingerprint(behavior: str, subject: str, input_state: Mapping[str, Any]) -> str:
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

    @staticmethod
    def validate_source(
        source: str,
        *,
        dependency_lock: str = "",
        skill_hashes: tuple[str, ...] = (),
        declared_action_class: str = "R0",
    ) -> SourceValidation:
        return validate_source(
            source,
            dependency_lock=dependency_lock,
            skill_hashes=skill_hashes,
            declared_action_class=declared_action_class,
        )

    def register_source(
        self,
        *,
        definition_id: str,
        name: str,
        success_check: str,
        source: str,
        dependency_lock: str = "",
        skill_hashes: tuple[str, ...] = (),
        action_class: str = "R0",
        principal: Principal | str | None = None,
    ) -> DefinitionVersion:
        """Validate and stage an immutable Python source snapshot."""

        self._require_writer()
        validation = validate_source(
            source,
            dependency_lock=dependency_lock,
            skill_hashes=skill_hashes,
            declared_action_class=action_class,
        )
        if not validation.accepted:
            raise SourceValidationError(validation)
        source_hash = validation.source_hash
        identity = revision_identity(source, dependency_lock, skill_hashes, validation)
        snapshot_path = Path("snapshots") / f"{identity}.py"
        if self._workspace is not None:
            target = self._workspace / snapshot_path
            target.parent.mkdir(parents=True, exist_ok=True)
            source_bytes = source.encode("utf-8")
            if target.exists() and target.read_bytes() != source_bytes:
                raise SourceValidationError(
                    SourceValidation(
                        False, ("immutable snapshot path collision",), source_hash=source_hash
                    )
                )
            if not target.exists():
                target.write_bytes(source_bytes)
        definition = AutomationDefinition(
            definition_id=definition_id,
            name=name,
            success_check=success_check,
            action_class=action_class,
            read_only=action_class == "R0",
            source_hash=source_hash,
            dependency_lock_hash=validation.dependency_lock_hash,
            skill_hashes=tuple(skill_hashes),
            validator_version=validation.validator_version,
            action_manifest=validation.action_manifest,
        )
        self._append(
            "rpa.source.snapshot.registered",
            {
                "definition_id": definition_id,
                "identity": identity,
                "source_hash": source_hash,
                "dependency_lock_hash": validation.dependency_lock_hash,
                "skill_hashes": list(skill_hashes),
                "validator_version": validation.validator_version,
                "action_manifest": validation.action_manifest.to_dict(),
                "snapshot_path": str(snapshot_path),
            },
        )
        proposal = AutomationProposal(
            proposal_id=f"source_{identity[:16]}",
            intent=AutomationIntent(
                intent_id=f"intent_{definition_id}",
                name=name,
                objective=success_check,
                required_capabilities=validation.action_manifest.capabilities or ("read",),
            ),
            discovery=DiscoveryEvidence(
                evidence_id=f"discovery_{identity[:16]}",
                selectors=(),
                observed_capabilities=validation.action_manifest.capabilities or ("read",),
            ),
            definition=definition,
        )
        return self.register_proposal(proposal, principal=principal)

    def run_snapshot(
        self,
        snapshot_path: str | Path,
        *,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> WorkerResponse:
        """Execute only a staged snapshot through the JSON worker protocol."""

        if self._workspace is None:
            raise PermissionError("worker execution requires a workspace-registered snapshot")
        snapshots_root = (self._workspace / "snapshots").resolve()
        supplied = Path(snapshot_path)
        path = (supplied if supplied.is_absolute() else self._workspace / supplied).resolve()
        try:
            path.relative_to(snapshots_root)
        except ValueError as exc:
            raise PermissionError("worker execution is restricted to registered snapshots") from exc
        if not path.exists():
            raise FileNotFoundError(f"immutable snapshot not found: {path}")
        registration = next(
            (
                event.payload
                for event in self._store.iter_events()
                if event.type == "rpa.source.snapshot.registered"
                and (self._workspace / str(event.payload.get("snapshot_path", ""))).resolve()
                == path
            ),
            None,
        )
        if registration is None:
            raise PermissionError("worker execution requires a registered snapshot")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != registration.get("source_hash"):
            raise PermissionError("registered snapshot content hash mismatch")
        request = WorkerRequest(
            request_id=request_id,
            snapshot_path=str(path),
            expected_source_hash=str(registration["source_hash"]),
            payload=dict(payload or {}),
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "harness.automation.worker", "--worker"],
                input=encode_request(request) + "\n",
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("automation worker timed out") from exc
        if completed.returncode != 0:
            raise RuntimeError(f"automation worker exited with status {completed.returncode}")
        return decode_response(completed.stdout.splitlines()[0], expected_request_id=request_id)

    def register_proposal(
        self,
        proposal: AutomationProposal,
        *,
        principal: Principal | str | None = None,
    ) -> DefinitionVersion:
        self._require_writer()
        caller = coerce_principal(principal)
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
        automation = next(
            (
                item
                for item in self._graph.objects(type="automation")
                if item.data.get("definition_id") == proposal.definition.definition_id
            ),
            None,
        )
        if automation is None:
            automation = self._graph.add_object(
                "automation",
                {
                    "definition_id": proposal.definition.definition_id,
                    "name": proposal.definition.name,
                    "action_class": proposal.definition.action_class,
                    "read_only": proposal.definition.read_only,
                    "status": "registered",
                },
                actor=caller.subject,
            )
        revision = self._graph.add_object(
            "automation_revision",
            {
                "definition_id": proposal.definition.definition_id,
                "version": version.version,
                "content_hash": version.content_hash,
                "source_hash": getattr(proposal.definition, "source_hash", ""),
                "immutable": True,
                "action_manifest": asdict(proposal.definition.action_manifest)
                if getattr(proposal.definition, "action_manifest", None)
                else {},
            },
            actor=caller.subject,
        )
        self._graph.add_relation(automation.id, revision.id, "has_revision", actor=caller.subject)
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
        principal: Principal | str | None = None,
    ) -> ApprovalGrant:
        """Record an immutable Approval Grant bound to one Definition Version."""

        self._require_writer()
        caller = require_operator(principal, "grant approval")
        if principal is not None and actor != caller.subject and caller.kind != "system":
            raise PrincipalError("approval actor must match the operator principal")
        definition_version = self._definition_version(definition_id, version)
        if definition_version is None:
            raise KeyError(f"Unknown definition version: {definition_id}@{version}")
        definition = definition_version.definition
        action_class = self._primary_action_class(definition)
        if action_class not in ALLOWED_ACTION_CLASSES:
            raise AuthorityError("missing or invalid action class")
        if action_class == "R4" and not governance_gate:
            raise AuthorityError("R4 requires a governance gate")
        if (
            action_class in WRITE_ACTION_CLASSES
            and action_class in {"R3", "R4"}
            and (not target_scope or not record_scope or not side_effect_scope)
        ):
            raise ApprovalError("write approvals require target, record, and side-effect scopes")
        expiry = (
            expires_at if isinstance(expires_at, str) else expires_at.astimezone(UTC).isoformat()
        )
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
        self._append(
            "rpa.approval.granted",
            {"approval_grant": grant.to_dict(), "principal": caller.to_dict()},
        )
        self._graph.add_object("approval_grant", grant.to_dict(), actor=caller.subject)
        return grant

    def execute_read_only(
        self,
        definition_id: str,
        adapter: ReadOnlyAdapter,
        verify: Callable[[ToolResult], VerificationResult],
        *,
        budget: RunBudget | None = None,
        principal: Principal | str | None = None,
        operation_id: str | None = None,
    ) -> RunSummary:
        self._require_writer()
        if not callable(verify):
            raise AuthorityError("explicit structured Verification callback is required")
        if principal is not None and coerce_principal(principal).kind not in {
            "agent",
            "operator",
            "scheduler",
            "system",
        }:
            raise PrincipalError("unsupported execution principal")
        definition = self._definition(definition_id)
        if definition is None:
            raise KeyError(f"Unknown automation definition: {definition_id}")
        if not definition.read_only or definition.action_class != "R0":
            raise AuthorityError("Only R0 read-only definitions are admitted by execute_read_only")
        if operation_id is not None:
            bound_actions = {
                definition.action_id,
                *(action.action_id for action in definition.actions),
            }
            if operation_id not in bound_actions:
                raise AuthorityError(
                    "requested operation is not bound to the registered definition"
                )

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
        self._graph.add_object(
            "action_attempt",
            {
                "run_id": run_id,
                "action_id": definition.action_id,
                "read_only": True,
                "action_class": definition.action_class,
                "idempotency_scope": definition.idempotency_scope or definition.action_id,
            },
            actor="system",
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
            verification = self._verify_result(verify, tool_result)
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
        principal: Principal | str | None = None,
    ) -> RunSummary:
        """Execute one approval-gated write with at-most-once admission and verification."""

        self._require_writer()
        if not callable(verify):
            raise AuthorityError("explicit structured Verification callback is required")
        caller = coerce_principal(principal)
        definition_version = self._definition_version(definition_id, version)
        if definition_version is None:
            raise KeyError(f"Unknown definition version: {definition_id}@{version}")
        definition = definition_version.definition
        action_class = self._primary_action_class(definition)
        if action_class not in ALLOWED_ACTION_CLASSES:
            raise AuthorityError("missing or invalid action class")
        if definition.read_only or action_class not in WRITE_ACTION_CLASSES:
            raise AuthorityError("execute_write admits only write-capable action classes")
        idempotency_scope = definition.idempotency_scope or (
            f"{definition.definition_id}:{version}:{definition.action_id}:{definition.record_scope}"
        )
        # The attempt is admitted before authority evaluation so a denied or
        # interrupted request is still auditable. It is not duplicate-write
        # authority until the explicit authority.admitted event below.
        run_id = f"run_{uuid4().hex}"
        self._append(
            "rpa.run.started",
            {
                "run_id": run_id,
                "definition_id": definition_id,
                "definition_version": version,
                "content_hash": definition_version.content_hash,
                "grant_id": grant_id,
                "read_only": False,
                "action_class": action_class,
                "principal": caller.to_dict(),
            },
        )
        self._append(
            "rpa.action.attempted",
            {
                "run_id": run_id,
                "action_id": definition.action_id,
                "read_only": False,
                "action_class": action_class,
                "idempotency_scope": idempotency_scope,
                "grant_id": grant_id,
                "authority_pending": True,
                "principal": caller.to_dict(),
            },
        )
        self._graph.add_object(
            "action_attempt",
            {
                "run_id": run_id,
                "action_id": definition.action_id,
                "read_only": False,
                "action_class": action_class,
                "idempotency_scope": idempotency_scope,
            },
            actor=caller.subject,
        )
        if action_class in {"R3", "R4"}:
            try:
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
            except Exception as exc:
                self._append("rpa.action.authority.denied", {"run_id": run_id, "error": str(exc)})
                self._append(
                    "rpa.run.failed", {"run_id": run_id, "failure_kind": "authority_denied"}
                )
                raise
        else:
            # R1/R2 may run under automatic authority when scopes match the definition.
            grant = self._approval_grant(grant_id)
            if grant is not None:
                try:
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
                except Exception as exc:
                    self._append(
                        "rpa.action.authority.denied", {"run_id": run_id, "error": str(exc)}
                    )
                    self._append(
                        "rpa.run.failed", {"run_id": run_id, "failure_kind": "authority_denied"}
                    )
                    raise
            else:
                self._append(
                    "rpa.action.authority.denied",
                    {"run_id": run_id, "error": "approval grant is required for write execution"},
                )
                self._append(
                    "rpa.run.failed", {"run_id": run_id, "failure_kind": "authority_denied"}
                )
                raise ApprovalError("approval grant is required for write execution")

        action = self._primary_action(definition)
        if self._write_already_admitted(definition.action_id, idempotency_scope):
            self._append("rpa.run.failed", {"run_id": run_id, "failure_kind": "duplicate_write"})
            raise DuplicateWriteError("write already admitted for run/action/idempotency scope")
        self._append(
            "rpa.action.authority.admitted",
            {
                "run_id": run_id,
                "grant_id": grant.grant_id,
                "actor": actor,
                "action_class": action_class,
            },
        )
        secrets = self._resolve_secrets(definition, action, secret_adapter)
        self._append(
            "rpa.action.dispatching",
            {
                "run_id": run_id,
                "action_id": definition.action_id,
                "definition_version": version,
                "grant_id": grant.grant_id,
                "idempotency_scope": idempotency_scope,
                "external_effect": True,
            },
        )
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
                write_outcome="unknown" if self._looks_like_transport_or_timeout(exc) else "failed",
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
        verification = self._verify_result(verify, tool_result)
        return self._finalize_run(
            run_id,
            tool_result,
            verification,
            definition_version=version,
            grant_id=grant.grant_id,
        )

    def propose_repair(
        self,
        *,
        parent_definition_id: str,
        parent_version: int,
        failure_run_id: str,
        failure_kind: str,
        discovery: DiscoveryEvidence,
        proposed_definition: AutomationDefinition,
        rationale: str = "",
        surface: str = "browser",
    ) -> RepairProposal:
        """Record a Repair Proposal bound to parent failure evidence; does not mutate parent."""

        self._require_writer()
        parent = self._definition_version(parent_definition_id, parent_version)
        if parent is None:
            raise KeyError(f"Unknown definition version: {parent_definition_id}@{parent_version}")
        failure = self._project_run(failure_run_id)
        if failure is None:
            raise KeyError(f"Unknown failure run: {failure_run_id}")
        self._validate_repair_selectors(proposed_definition, discovery, surface)
        candidate_run_id, candidate_runtime = self._fork_canonical("repair-candidate")
        proposal = RepairProposal(
            repair_id=f"repair_{uuid4().hex}",
            parent_definition_id=parent_definition_id,
            parent_version=parent_version,
            parent_content_hash=parent.content_hash,
            failure_run_id=failure_run_id,
            failure_kind=failure_kind,
            discovery=discovery,
            proposed_definition=proposed_definition,
            rationale=rationale,
            surface=surface,
            candidate_run_id=candidate_run_id,
        )
        self._append("rpa.repair.proposed", {"repair_proposal": proposal.to_dict()})
        if candidate_runtime is not None:
            candidate_runtime.graph.add_object(
                "automation_revision",
                {
                    "definition_id": proposed_definition.definition_id,
                    "version": parent.version + 1,
                    "content_hash": content_hash(proposed_definition),
                    "immutable": True,
                    "source_hash": proposed_definition.source_hash,
                    "action_manifest": asdict(proposed_definition.action_manifest)
                    if proposed_definition.action_manifest
                    else {},
                },
                actor="repair-agent",
            )
        return proposal

    def trial_repair(
        self,
        repair_id: str,
        *,
        adapter: ReadOnlyAdapter | WriteAdapter,
        verify: Callable[[ToolResult], VerificationResult],
        budget: RunBudget | None = None,
        replay_cache: Mapping[str, ToolResult] | None = None,
        secret_adapter: SecretAdapter | None = None,
        actor: str | None = None,
        grant_id: str | None = None,
    ) -> RepairTrialResult:
        """Execute a bounded repair trial in an isolated fork without promoting the parent."""

        self._require_writer()
        proposal = self._repair_proposal(repair_id)
        if proposal is None:
            raise KeyError(f"Unknown repair proposal: {repair_id}")
        parent = self._definition_version(proposal.parent_definition_id, proposal.parent_version)
        if parent is None:
            raise RepairError("parent definition missing for trial")
        if parent.content_hash != proposal.parent_content_hash:
            raise RepairError("stale parent conflict: content hash changed")
        trial_budget = budget or RunBudget(
            max_model_proposals=1,
            max_tool_calls=3,
            max_action_attempts=2,
            max_verification_attempts=2,
            max_repair_trials=1,
        )
        self._validate_run_budget(trial_budget)
        prior_trials = self._repair_trial_count(repair_id)
        trial_id = f"trial_{uuid4().hex}"
        trial_run_id: str | None = None
        candidate_runtime = (
            self._load_fork(proposal.candidate_run_id) if proposal.candidate_run_id else None
        )
        if candidate_runtime is not None and candidate_runtime.graph.events:
            try:
                trial_runtime = candidate_runtime.fork(
                    candidate_runtime.graph.events[-1].id,
                    label="repair-trial",
                )
                trial_run_id = trial_runtime.run_id
            except Exception:
                trial_run_id = None
        self._append(
            "rpa.repair.trial.started",
            {
                "trial_id": trial_id,
                "repair_id": repair_id,
                "budget": trial_budget.to_dict(),
                "parent_definition_id": proposal.parent_definition_id,
                "parent_version": proposal.parent_version,
                "candidate_run_id": proposal.candidate_run_id,
                "trial_run_id": trial_run_id,
            },
        )
        if prior_trials >= trial_budget.max_repair_trials:
            result = RepairTrialResult(
                trial_id=trial_id,
                repair_id=repair_id,
                status="failed",
                verification={
                    "passed": False,
                    "message": f"repair trial budget exhausted ({prior_trials})",
                },
                evidence_references=(),
                parent_diff=self._repair_diff(parent.definition, proposal.proposed_definition),
                failure_kind="budget_exhausted",
                parent_run_id=proposal.candidate_run_id,
            )
            self._append("rpa.repair.trial.finished", {"trial": result.to_dict()})
            return result
        # Fork identity is the trial_id; parent graph remains untouched.
        self.admit_transition(
            self._ensure_trial_run(trial_id, proposal, trial_budget),
            behavior="repair_trial",
            subject=repair_id,
            input_state={"trial_id": trial_id, "parent": proposal.parent_content_hash},
            budget_dimension="repair_trials",
            run_budget=trial_budget,
        )

        definition = proposal.proposed_definition
        if definition.action_class in WRITE_ACTION_CLASSES:
            if grant_id is None or actor is None:
                raise RepairError(
                    "write repair trial requires grant_id and actor within parent scope"
                )
            grant = self._approval_grant(grant_id)
            if grant is None:
                raise RepairError("trial tools cannot exceed parent Approval Grant scope")
            if (
                grant.definition_id != proposal.parent_definition_id
                or grant.definition_version != proposal.parent_version
            ):
                raise RepairError("trial tools cannot exceed parent Approval Grant scope")

        cache_key = f"{repair_id}:{proposal.parent_content_hash}"
        try:
            if replay_cache is not None and cache_key in replay_cache:
                tool_result = replay_cache[cache_key]
                self._append(
                    "rpa.repair.trial.replayed",
                    {"trial_id": trial_id, "repair_id": repair_id, "cache_key": cache_key},
                )
            elif definition.read_only or definition.action_class == "R0":
                tool_result = adapter(definition, trial_id)  # type: ignore[call-arg]
            else:
                secrets = self._resolve_secrets(
                    definition, self._primary_action(definition), secret_adapter
                )
                tool_result = adapter(  # type: ignore[call-arg]
                    definition, trial_id, secrets=secrets, action=self._primary_action(definition)
                )
            verification = self._verify_result(verify, tool_result)
        except Exception as exc:
            tool_result = ToolResult(evidence={"error": str(exc)})
            verification = VerificationResult(
                passed=False,
                message="repair trial failed",
                failure_kind="trial_error",
                evidence={"error": str(exc)},
            )

        evidence_id = f"evidence_{uuid4().hex}"
        uri = f"evidence/repair/{trial_id}.json"
        reference = EvidenceReference(evidence_id=evidence_id, uri=uri, kind="repair_trial")
        self._append(
            "rpa.evidence.referenced",
            {"run_id": trial_id, "evidence": asdict(reference)},
        )
        if self._workspace is not None:
            path = self._workspace / uri
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    redact_value(
                        {
                            "trial_id": trial_id,
                            "tool_evidence": tool_result.evidence,
                            "verification": asdict(verification),
                        }
                    ),
                    indent=2,
                ),
                encoding="utf-8",
            )
        status = "passed" if verification.passed else "failed"
        result = RepairTrialResult(
            trial_id=trial_id,
            repair_id=repair_id,
            status=status,
            verification={
                "passed": verification.passed,
                "message": verification.message,
                "failure_kind": verification.failure_kind,
            },
            evidence_references=(reference,),
            parent_diff=self._repair_diff(parent.definition, definition),
            failure_kind=None
            if verification.passed
            else (verification.failure_kind or "trial_failed"),
            parent_run_id=proposal.candidate_run_id,
        )
        if trial_run_id is not None:
            result = RepairTrialResult(
                trial_id=result.trial_id,
                repair_id=result.repair_id,
                status=result.status,
                verification=result.verification,
                evidence_references=result.evidence_references,
                parent_diff=result.parent_diff,
                failure_kind=result.failure_kind,
                parent_run_id=trial_run_id,
            )
        self._append("rpa.repair.trial.finished", {"trial": result.to_dict()})
        return result

    def promote_repair(
        self,
        repair_id: str,
        *,
        trial_id: str,
        principal: Principal | str | None = None,
    ) -> DefinitionVersion:
        """Promote a successful repair trial into a new immutable Definition Version."""

        self._require_writer()
        require_operator(principal, "promote repair")
        proposal = self._repair_proposal(repair_id)
        if proposal is None:
            raise KeyError(f"Unknown repair proposal: {repair_id}")
        trial = self._repair_trial(trial_id)
        if trial is None or trial["repair_id"] != repair_id:
            raise RepairError("trial not found for repair")
        if trial["status"] != "passed" or not trial["verification"].get("passed"):
            raise RepairError("promotion requires passing verification")
        parent = self._definition_version(proposal.parent_definition_id, proposal.parent_version)
        if parent is None:
            raise RepairError("parent missing")
        if parent.content_hash != proposal.parent_content_hash:
            raise RepairError("stale parent conflict: content hash changed")
        current_versions = self.definition_versions(proposal.parent_definition_id)
        latest = current_versions[-1] if current_versions else None
        if (
            latest is not None
            and latest.version != proposal.parent_version
            and latest.content_hash != proposal.parent_content_hash
        ):
            raise RepairError("stale parent conflict: newer non-matching version exists")
        # No unresolved ambiguity on discovery.
        if any(
            selector.strategy in WEAK_REPAIR_STRATEGIES and not selector.verified
            for selector in proposal.discovery.selectors
        ):
            raise RepairError("unresolved selector ambiguity")
        version = DefinitionVersion(
            definition=proposal.proposed_definition,
            version=len(current_versions) + 1,
            content_hash=content_hash(proposal.proposed_definition),
            proposal_id=proposal.repair_id,
        )
        promotion_marker: str | None = None
        if proposal.candidate_run_id is not None:
            candidate_runtime = self._load_fork(proposal.candidate_run_id)
            if candidate_runtime is not None:
                try:
                    plan = self._runtime.promote(candidate_runtime, dry_run=True)
                    if not plan.is_promotable:
                        raise RepairError("ActiveGraph candidate promotion has conflicts")
                    applied = self._runtime.promote(candidate_runtime)
                    promotion_marker = applied.marker_event_id
                except RepairError:
                    raise
                except Exception as exc:
                    raise RepairError(f"ActiveGraph candidate promotion failed: {exc}") from exc
        self._append(
            "rpa.definition.version.registered",
            {"definition_version": asdict(version)},
        )
        self._append(
            "rpa.repair.promoted",
            {
                "repair_id": repair_id,
                "trial_id": trial_id,
                "definition_version": version.version,
                "content_hash": version.content_hash,
                "parent_version": proposal.parent_version,
                "promotion_marker": promotion_marker,
            },
        )
        return version

    def reject_repair(
        self,
        repair_id: str,
        *,
        reason: str,
        trial_id: str | None = None,
        principal: Principal | str | None = None,
    ) -> None:
        self._require_writer()
        require_operator(principal, "reject repair")
        proposal = self._repair_proposal(repair_id)
        if proposal is None:
            raise KeyError(f"Unknown repair proposal: {repair_id}")
        parent_before = self.definition_versions(proposal.parent_definition_id)
        self._append(
            "rpa.repair.rejected",
            {
                "repair_id": repair_id,
                "trial_id": trial_id,
                "reason": reason,
                "parent_definition_id": proposal.parent_definition_id,
                "parent_version": proposal.parent_version,
            },
        )
        parent_after = self.definition_versions(proposal.parent_definition_id)
        if parent_before != parent_after:
            raise RepairError("rejection mutated parent definition versions")

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
                failure_kind=None if result.conclusion == "applied" else "needs_reconciliation",
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
        verification = self._verify_result(verify, synthetic)
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

    def replay_run(
        self,
        run_id: str,
        *,
        adapter: Callable[..., Any] | None = None,
    ) -> RunSummary:
        """Replay a completed run from accepted boundary results.

        ``adapter`` is intentionally ignored for completed boundaries. Keeping
        it in the signature lets callers use the same wiring for live and
        replayed runs while making accidental external reinvocation impossible.
        """

        state = self._project_run(run_id)
        if state is None:
            raise KeyError(f"Unknown run: {run_id}")
        if state["status"] not in {"completed", "failed"}:
            raise ReplayDivergenceError(
                f"run {run_id} is not replayable from terminal status {state['status']}"
            )
        returned = [
            event
            for event in self._graph.events
            if event.type == "rpa.action.returned" and event.payload.get("run_id") == run_id
        ]
        if not returned and state["status"] == "completed":
            raise ReplayDivergenceError("completed run has no recorded boundary result")
        self._append(
            "rpa.run.replayed",
            {
                "run_id": run_id,
                "boundary_count": len(returned),
                "adapter_invoked": False,
            },
        )
        return self.inspect_run(run_id)

    replay = replay_run

    def record_observation(
        self,
        run_id: str,
        *,
        call_id: str,
        inputs: Mapping[str, Any],
        adapter: Callable[[], ToolResult],
        replay: bool = False,
    ) -> ToolResult:
        """Admit and record an Observation, or return its exact replay value."""

        input_hash = self._input_state_hash(inputs)
        if replay:
            for event in self._graph.events:
                if (
                    event.type != "rpa.observation.returned"
                    or event.payload.get("run_id") != run_id
                ):
                    continue
                if (
                    event.payload.get("call_id") != call_id
                    or event.payload.get("input_hash") != input_hash
                ):
                    continue
                return ToolResult(
                    value=dict(event.payload.get("value") or {}),
                    evidence=dict(event.payload.get("evidence") or {}),
                )
            raise ReplayDivergenceError(f"no recorded Observation matches call {call_id}")
        self._append(
            "rpa.observation.accepted",
            {"run_id": run_id, "call_id": call_id, "input_hash": input_hash},
        )
        result = adapter()
        if not isinstance(result, ToolResult):
            raise TypeError("Observation adapter must return ToolResult")
        self._append(
            "rpa.observation.returned",
            {
                "run_id": run_id,
                "call_id": call_id,
                "input_hash": input_hash,
                "value": result.value,
                "evidence": result.evidence,
            },
        )
        return result

    @staticmethod
    def boundary_call_id(
        revision_identity_value: str,
        run_id: str,
        logical_site: str,
        resource: str,
        inputs: Mapping[str, Any],
    ) -> str:
        material = {
            "revision": revision_identity_value,
            "run_id": run_id,
            "logical_site": logical_site,
            "resource": resource,
            "inputs": inputs,
        }
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    def record_clock(self, run_id: str, *, call_id: str, replay: bool = False) -> str:
        if replay:
            for event in self._graph.events:
                if (
                    event.type == "rpa.clock.read"
                    and event.payload.get("run_id") == run_id
                    and event.payload.get("call_id") == call_id
                ):
                    return str(event.payload["value"])
            raise ReplayDivergenceError(f"no recorded clock value matches call {call_id}")
        value = datetime.now(UTC).isoformat()
        self._append("rpa.clock.read", {"run_id": run_id, "call_id": call_id, "value": value})
        return value

    def record_random(self, run_id: str, *, call_id: str, replay: bool = False) -> float:
        if replay:
            for event in self._graph.events:
                if (
                    event.type == "rpa.random.read"
                    and event.payload.get("run_id") == run_id
                    and event.payload.get("call_id") == call_id
                ):
                    return float(event.payload["value"])
            raise ReplayDivergenceError(f"no recorded random value matches call {call_id}")
        import random

        value = random.random()
        self._append("rpa.random.read", {"run_id": run_id, "call_id": call_id, "value": value})
        return value

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
        self._graph.emit(
            Event(
                id=event_id,
                type=event_type,
                payload=redact_value(payload),
                actor="application",
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

        events = list(self._store.iter_events())
        matching_attempts: set[str] = set()
        admitted = False
        for event in events:
            payload = event.payload
            if event.type == "rpa.action.attempted":
                if (
                    not payload.get("read_only")
                    and payload.get("action_id") == action_id
                    and payload.get("idempotency_scope") == idempotency_scope
                ):
                    matching_attempts.add(str(payload.get("run_id")))
            elif event.type == "rpa.action.authority.admitted":
                if str(payload.get("run_id")) in matching_attempts:
                    admitted = True
            elif (
                event.type == "rpa.reconciliation.not_applied"
                and payload.get("action_id") == action_id
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

    def _repair_proposal(self, repair_id: str) -> RepairProposal | None:
        for event in self._store.iter_events():
            if event.type != "rpa.repair.proposed":
                continue
            payload = event.payload["repair_proposal"]
            if payload["repair_id"] != repair_id:
                continue
            discovery_value = payload["discovery"]
            definition = self._definition_from_payload(payload["proposed_definition"])
            return RepairProposal(
                repair_id=payload["repair_id"],
                parent_definition_id=payload["parent_definition_id"],
                parent_version=payload["parent_version"],
                parent_content_hash=payload["parent_content_hash"],
                failure_run_id=payload["failure_run_id"],
                failure_kind=payload["failure_kind"],
                discovery=DiscoveryEvidence(
                    evidence_id=discovery_value["evidence_id"],
                    selectors=tuple(
                        SelectorEvidence(**item) for item in discovery_value.get("selectors", ())
                    ),
                    observed_capabilities=tuple(discovery_value.get("observed_capabilities", ())),
                    schema_version=discovery_value.get("schema_version", "v1"),
                ),
                proposed_definition=definition,
                rationale=payload.get("rationale", ""),
                surface=payload.get("surface", "browser"),
                candidate_run_id=payload.get("candidate_run_id"),
            )
        return None

    def _repair_trial(self, trial_id: str) -> dict[str, Any] | None:
        for event in self._store.iter_events():
            if event.type != "rpa.repair.trial.finished":
                continue
            trial = event.payload["trial"]
            if trial["trial_id"] == trial_id:
                return trial
        return None

    def _repair_trial_count(self, repair_id: str) -> int:
        count = 0
        for event in self._store.iter_events():
            if event.type != "rpa.repair.trial.finished":
                continue
            if event.payload.get("trial", {}).get("repair_id") == repair_id:
                count += 1
        return count

    def _ensure_trial_run(self, trial_id: str, proposal: RepairProposal, budget: RunBudget) -> str:
        self._append(
            "rpa.run.started",
            {
                "run_id": trial_id,
                "definition_id": proposal.parent_definition_id,
                "read_only": proposal.proposed_definition.read_only,
                "budget": budget.to_dict(),
                "repair_id": proposal.repair_id,
                "fork": True,
            },
        )
        return trial_id

    @staticmethod
    def _repair_diff(
        parent: AutomationDefinition, proposed: AutomationDefinition
    ) -> dict[str, Any]:
        return {
            "parent": asdict(parent),
            "proposed": asdict(proposed),
            "content_hash_parent": content_hash(parent),
            "content_hash_proposed": content_hash(proposed),
        }

    def _validate_repair_selectors(
        self,
        definition: AutomationDefinition,
        discovery: DiscoveryEvidence,
        surface: str,
    ) -> None:
        priority = BROWSER_SELECTOR_PRIORITY if surface == "browser" else DESKTOP_SELECTOR_PRIORITY
        for selector in discovery.selectors:
            if selector.strategy not in priority:
                raise RepairError(f"selector strategy not in {surface} priority ladder")
            if selector.strategy in WEAK_REPAIR_STRATEGIES and not selector.verified:
                raise RepairError("rejected weak selector: unverified weak strategy")
        for action in definition.actions:
            if action.selector is None:
                continue
            if action.selector.strategy not in priority:
                raise RepairError(f"selector strategy not in {surface} priority ladder")
            if action.selector.strategy in WEAK_REPAIR_STRATEGIES and not action.selector.verified:
                raise RepairError("rejected weak selector: unverified weak strategy")

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
        self._graph.add_object(
            "verification_result",
            {
                "run_id": run_id,
                "passed": verification.passed,
                "failure_kind": verification.failure_kind,
            },
            actor="verifier",
        )
        reference = self._record_evidence(run_id, tool_result, verification)
        run_object = next(
            (
                item
                for item in self._graph.objects(type="workflow_run")
                if item.data.get("run_id") == run_id
            ),
            None,
        )
        evidence_object = next(
            (
                item
                for item in self._graph.objects(type="evidence_reference")
                if item.data.get("evidence_id") == reference.evidence_id
            ),
            None,
        )
        if run_object is not None and evidence_object is not None:
            self._graph.add_relation(run_object.id, evidence_object.id, "evidences", actor="system")
        self._patch_workflow_status(run_id, "completed" if verification.passed else "failed")
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

    def _patch_workflow_status(self, run_id: str, status: str) -> None:
        for item in self._graph.objects(type="workflow_run"):
            if item.data.get("run_id") == run_id:
                self._graph.patch_object(item.id, {"status": status}, actor="application")
                return

    @staticmethod
    def _primary_action(definition: AutomationDefinition) -> AutomationAction | None:
        for action in definition.actions:
            if action.action_id == definition.action_id:
                return action
        return definition.actions[0] if definition.actions else None

    @staticmethod
    def _verify_result(
        verify: Callable[[ToolResult], VerificationResult],
        tool_result: ToolResult,
    ) -> VerificationResult:
        try:
            result = verify(tool_result)
        except Exception as exc:
            return VerificationResult(
                passed=False,
                message="Verification callback failed",
                failure_kind="verifier_error",
                evidence={"error": str(exc)},
            )
        if not isinstance(result, VerificationResult):
            return VerificationResult(
                passed=False,
                message="Verification callback returned an invalid result",
                failure_kind="verifier_error",
                evidence={"type": type(result).__name__},
            )
        return result

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
        manifest = value.get("action_manifest")
        if isinstance(manifest, Mapping):
            from harness.automation.source_validation import ActionManifest

            value["action_manifest"] = ActionManifest(**manifest)
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
        artifact = {
            "tool_evidence": tool_result.evidence,
            "verification_evidence": verification.evidence,
            "verification": {
                "passed": verification.passed,
                "message": verification.message,
                "failure_kind": verification.failure_kind,
            },
        }
        if self._workspace is not None:
            from harness.automation.evidence import EvidenceStore

            digest, size, path = EvidenceStore(self._workspace / "evidence").put(artifact)
            uri = str(path.relative_to(self._workspace))
        else:
            encoded = json.dumps(redact_value(artifact), sort_keys=True, default=str).encode()
            digest = hashlib.sha256(encoded).hexdigest()
            size = len(encoded)
            uri = f"evidence/artifacts/sha256/{digest[:2]}/{digest}.json"
        reference = EvidenceReference(
            evidence_id=evidence_id,
            uri=uri,
            kind="verification",
            content_hash=digest,
            size=size,
        )
        self._append(
            "rpa.evidence.referenced",
            {"run_id": run_id, "evidence": asdict(reference)},
        )
        self._graph.add_object(
            "evidence_reference",
            {
                "evidence_id": evidence_id,
                "run_id": run_id,
                "uri": uri,
                "content_hash": digest,
                "size": size,
            },
            actor="system",
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
                elif event.type == "rpa.action.dispatching":
                    state["status"] = "needs_reconciliation"
                    state["failure_kind"] = "needs_reconciliation"
                    state["blocked_reason"] = (
                        "external effect may have been dispatched before process recovery"
                    )
                    state["next_required"] = "reconcile the dispatch before retrying"
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
