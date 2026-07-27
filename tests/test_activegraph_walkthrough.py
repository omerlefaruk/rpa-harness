"""
ActiveGraph walkthrough — how rpa-harness uses the event log as lifecycle authority.

Run with narration:
  .venv\\Scripts\\python.exe -m pytest tests/test_activegraph_walkthrough.py -q -s

What ActiveGraph is doing here
------------------------------
ActiveGraph provides an EventStore. Every product decision is an *append-only event*.
The graph / RunSummary are *projections* rebuilt by replaying those events.

  adapters (CLI/MCP/tests)
           │
           ▼
  AutomationApplication   ← only writer of lifecycle events
           │
           ▼
  EventStore.append(Event(type=..., payload=...))
           │
           ▼
  inspect_run() / definition_versions()  ← fold events into a view

Tools (browser/API/desktop fakes) return ToolResult only. They never write events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from activegraph import Graph, Runtime
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    MappingSecretAdapter,
    SelectorEvidence,
    ToolResult,
    VerificationResult,
)
from harness.automation.pack import pack


def _events(app: AutomationApplication) -> list[tuple[str, dict]]:
    """Read the authoritative ActiveGraph event stream."""
    return [(event.type, dict(event.payload)) for event in app._store.iter_events()]


def _print_story(title: str, lines: list[str]) -> None:
    print(f"\n=== {title} ===")
    for line in lines:
        print(f"  {line}")


def test_activegraph_walkthrough_read_then_approval_gated_write(capsys):
    """
    Full story in one test:

    1. Bind an in-memory ActiveGraph EventStore (same contract as workspace SQLite).
    2. Load the first-party pack (typed objects/tools declaration).
    3. Author a write definition as a proposal → validate → register version (events).
    4. Grant approval bound to that exact version/hash/scopes (event).
    5. Execute write: Action Attempt *before* tool I/O, then return, verify, evidence.
    6. Prove the event log is the authority: inspect_run is only a projection.
    """

    # --- 1) ActiveGraph store: sole lifecycle authority for this workspace ---
    store = InMemoryEventStore(run_id="walkthrough")
    app = AutomationApplication(store=store)

    # --- 2) Pack is a typed declaration; Runtime can load it (host still owns adapters) ---
    runtime = Runtime(Graph(), store=InMemoryEventStore(run_id="pack_demo"))
    runtime.load_pack(pack)
    pack_tool_names = {tool.name for tool in pack.tools}
    assert "read_only_action" in pack_tool_names
    assert "approval_gated_write" in pack_tool_names

    # --- 3) Authoring: intent + discovery evidence + proposed definition ---
    # Discovery is *evidence*, not executable truth. The deterministic compiler
    # (validate_proposal / register_proposal) admits a Definition Version.
    proposal = AutomationProposal(
        proposal_id="walk-proposal-1",
        intent=AutomationIntent(
            intent_id="walk-intent",
            name="Update inventory qty",
            objective="Set SKU qty after operator approval",
            required_capabilities=("write",),
        ),
        discovery=DiscoveryEvidence(
            evidence_id="walk-discovery",
            selectors=(SelectorEvidence("role", "Save", True),),
            observed_capabilities=("write",),
        ),
        definition=AutomationDefinition(
            definition_id="walk-write",
            name="Update inventory qty",
            success_check="qty equals 7",
            action_id="update-qty",
            action_class="R3",  # R3 always needs an Approval Grant
            read_only=False,
            target_scope="warehouse-a",
            record_scope="sku-42",
            side_effect_scope="inventory.qty",
            idempotency_scope="walk-write:sku-42",
            credential_names=("api_token",),
            actions=(
                AutomationAction(
                    action_id="update-qty",
                    capability="write",
                    action_class="R3",
                    success_check="qty equals 7",
                    selector=SelectorEvidence("role", "Save", True),
                    credential_names=("api_token",),
                    # Secret *reference* only — never plaintext in the proposal/events
                    inputs={"password": "${secrets.api_token}", "qty": 7},
                ),
            ),
        ),
    )

    validation = app.validate_proposal(proposal)
    assert validation.accepted, validation.errors

    version = app.register_proposal(proposal)
    # register_proposal appends: rpa.definition.version.registered
    assert version.version == 1
    assert len(version.content_hash) == 64  # sha256 hex

    # --- 4) Approval Grant: immutable fact bound to *this* version + scopes ---
    grant = app.grant_approval(
        definition_id=version.definition.definition_id,
        version=version.version,
        actor="operator@example",
        target_scope="warehouse-a",
        record_scope="sku-42",
        side_effect_scope="inventory.qty",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        action_id="update-qty",
    )
    # appends: rpa.approval.granted

    # --- 5) Execution edge: secret handle resolves only here ---
    secret_adapter = MappingSecretAdapter({"api_token": "super-secret-value"})
    tool_calls: list[str] = []

    def write_adapter(definition, run_id, *, secrets, action):
        """
        This stands in for a real browser/API/desktop tool.

        Important ActiveGraph rule in this product:
        - tools return data (ToolResult)
        - tools do NOT append lifecycle events
        - AutomationApplication already recorded Action Attempt *before* this runs
        """
        tool_calls.append(run_id)
        # Agent-facing surfaces never see plaintext; only this edge may reveal().
        assert "api_token" in secrets
        assert str(secrets["api_token"]) == "[REDACTED]"
        assert secrets["api_token"].reveal() == "super-secret-value"
        return ToolResult(
            value={"qty": 7},
            evidence={"password": "super-secret-value", "status": "written"},
            write_outcome="applied",
        )

    summary = app.execute_write(
        "walk-write",
        version=version.version,
        grant_id=grant.grant_id,
        adapter=write_adapter,
        verify=lambda result: VerificationResult(
            passed=result.value.get("qty") == 7,
            message="qty matches target",
            evidence={"expected": 7, "token": "should-be-redacted"},
        ),
        actor="operator@example",
        secret_adapter=secret_adapter,
    )

    # --- 6) Projection: inspect_run folds events; it is not a second source of truth ---
    assert summary.status == "completed"
    assert summary.grant_id == grant.grant_id
    assert summary.definition_version == 1
    assert len(summary.evidence_references) == 1
    assert len(tool_calls) == 1
    # Redaction: secret never appears in agent-visible summary
    assert "super-secret-value" not in str(summary.to_dict())

    projected = app.inspect_run(summary.run_id)
    assert projected.to_dict() == summary.to_dict()

    # --- 7) Read the EventStore: this is "how ActiveGraph is used" ---
    stream = _events(app)
    types = [event_type for event_type, _ in stream]

    # Expected lifecycle spine for this walkthrough
    assert "rpa.definition.version.registered" in types
    assert "rpa.approval.granted" in types
    assert "rpa.run.started" in types
    assert "rpa.action.attempted" in types  # before tool I/O
    assert "rpa.action.returned" in types
    assert "rpa.verification.recorded" in types
    assert "rpa.evidence.referenced" in types
    assert "rpa.run.completed" in types

    # Action attempt must appear before the tool return in the log
    assert types.index("rpa.action.attempted") < types.index("rpa.action.returned")

    # No plaintext secret in any event payload (EventStore is also redacted)
    blob = str(stream)
    assert "super-secret-value" not in blob

    # Duplicate write with same idempotency scope is refused without another tool call
    with pytest.raises(Exception) as dup:
        app.execute_write(
            "walk-write",
            version=version.version,
            grant_id=grant.grant_id,
            adapter=write_adapter,
            verify=lambda result: VerificationResult(passed=True),
            actor="operator@example",
            secret_adapter=secret_adapter,
        )
    assert "duplicate" in str(dup.value).lower() or "already admitted" in str(dup.value).lower()
    assert len(tool_calls) == 1  # tool not invoked again

    # Narration for -s runs
    _print_story(
        "ActiveGraph event spine (authoritative)",
        [f"{i+1:02d}. {event_type}" for i, event_type in enumerate(types)],
    )
    _print_story(
        "What each layer did",
        [
            "EventStore: append-only log of lifecycle facts",
            "AutomationApplication: only component allowed to append those facts",
            "Write adapter: external I/O only; returned ToolResult; no event writes",
            "inspect_run: projection of the log for this run_id",
            f"Run {summary.run_id} → status={summary.status}",
            f"Approval grant {grant.grant_id} bound to version={version.version} hash={version.content_hash[:12]}…",
        ],
    )

    # Force output to show under -s when desired; still silent under normal pytest
    captured = capsys.readouterr()
    assert "rpa.run.completed" in types
    # keep captured for local debugging if someone re-runs with prints only
    del captured


def test_activegraph_sqlite_workspace_is_same_contract(tmp_path):
    """
    Same application API, durable ActiveGraph store on disk.

    Workspace layout (projections, not authority):
      <workspace>/data/automation-events.sqlite   ← EventStore
      <workspace>/evidence/<run_id>.json           ← blob refs from events
    """
    workspace = tmp_path / "ag-workspace"
    app = AutomationApplication(workspace)
    app.register_definition(
        AutomationDefinition(
            definition_id="walk-read",
            name="Read count",
            success_check="count present",
        )
    )
    summary = app.execute_read_only(
        "walk-read",
        lambda _d, _r: ToolResult(value={"count": 3}, evidence={"source": "fixture"}),
        lambda result: VerificationResult(
            passed="count" in result.value, message="count present"
        ),
    )
    app.close()

    assert summary.status == "completed"
    db = workspace / "data" / "automation-events.sqlite"
    assert db.exists(), "SQLite EventStore is the durable ActiveGraph log"
    evidence_path = workspace / summary.evidence_references[0].uri
    assert evidence_path.exists(), "evidence blobs are referenced by events, not embedded"

    # Re-open read-only: second process projects the same run from the log
    inspector = AutomationApplication(workspace, read_only=True)
    try:
        again = inspector.inspect_run(summary.run_id)
    finally:
        inspector.close()
    assert again.status == "completed"
    assert again.to_dict() == summary.to_dict()
