"""Ambiguous write outcomes and reconciliation without duplicate writes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AmbiguousWriteError,
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    DuplicateWriteError,
    MappingSecretAdapter,
    ReconciliationResult,
    SelectorEvidence,
    ToolResult,
    VerificationResult,
)


def write_definition(**changes):
    values = {
        "definition_id": "inventory-write",
        "name": "Update inventory",
        "success_check": "inventory count equals target",
        "action_id": "update-inventory",
        "action_class": "R3",
        "read_only": False,
        "target_scope": "warehouse-a",
        "record_scope": "sku-1",
        "side_effect_scope": "inventory.qty",
        "idempotency_scope": "inventory-write:sku-1",
        "credential_names": ("api_token",),
        "actions": (
            AutomationAction(
                action_id="update-inventory",
                capability="write",
                action_class="R3",
                success_check="inventory count equals target",
                credential_names=("api_token",),
                inputs={"password": "${secrets.api_token}", "qty": 7},
            ),
        ),
    }
    values.update(changes)
    return AutomationDefinition(**values)


def write_proposal(definition=None):
    definition = definition or write_definition()
    return AutomationProposal(
        proposal_id="proposal_write_1",
        intent=AutomationIntent(
            intent_id="intent_write_1",
            name="Update inventory",
            objective="Set inventory quantity",
            required_capabilities=("write",),
        ),
        discovery=DiscoveryEvidence(
            evidence_id="discovery_write_1",
            selectors=(SelectorEvidence("role", "save", True),),
            observed_capabilities=("write",),
        ),
        definition=definition,
    )


class RecordingWriteAdapter:
    def __init__(self, behavior="ok"):
        self.behavior = behavior
        self.calls = 0

    def __call__(self, definition, run_id, *, secrets, action):
        self.calls += 1
        if self.behavior == "timeout":
            raise TimeoutError("timed out after possible write")
        if self.behavior == "transport":
            raise ConnectionError("transport lost mid-write")
        if self.behavior == "malformed":
            raise ValueError("malformed incomplete response")
        if self.behavior == "ambiguous":
            raise AmbiguousWriteError(
                "process interrupted", evidence={"stage": "after_send"}
            )
        if self.behavior == "unknown_result":
            return ToolResult(value={}, evidence={"raw": "?"}, write_outcome="unknown")
        return ToolResult(value={"qty": 7}, evidence={"status": "written"}, write_outcome="applied")


def setup_write(app, behavior="ok"):
    version = app.register_proposal(write_proposal())
    grant = app.grant_approval(
        definition_id=version.definition.definition_id,
        version=version.version,
        actor="operator@example",
        target_scope=version.definition.target_scope,
        record_scope=version.definition.record_scope,
        side_effect_scope=version.definition.side_effect_scope,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        action_id=version.definition.action_id,
    )
    adapter = RecordingWriteAdapter(behavior)
    return version, grant, adapter


def execute(app, version, grant, adapter):
    return app.execute_write(
        version.definition.definition_id,
        version=version.version,
        grant_id=grant.grant_id,
        adapter=adapter,
        verify=lambda result: VerificationResult(
            passed=result.value.get("qty") == 7, message="qty check"
        ),
        actor="operator@example",
        secret_adapter=MappingSecretAdapter({"api_token": "secret"}),
    )


@pytest.mark.parametrize("behavior", ["timeout", "transport", "malformed", "ambiguous", "unknown_result"])
def test_unknown_write_outcomes_need_reconciliation(behavior):
    app = AutomationApplication(store=InMemoryEventStore())
    version, grant, adapter = setup_write(app, behavior)
    summary = execute(app, version, grant, adapter)
    assert summary.status == "needs_reconciliation"
    assert summary.failure_kind == "needs_reconciliation"
    assert adapter.calls == 1


def test_no_retry_while_reconciliation_unresolved():
    app = AutomationApplication(store=InMemoryEventStore())
    version, grant, adapter = setup_write(app, "timeout")
    first = execute(app, version, grant, adapter)
    assert first.status == "needs_reconciliation"
    with pytest.raises(DuplicateWriteError):
        execute(app, version, grant, adapter)
    assert adapter.calls == 1


def test_reconciliation_applied_verifies_without_second_write():
    app = AutomationApplication(store=InMemoryEventStore())
    version, grant, adapter = setup_write(app, "ambiguous")
    summary = execute(app, version, grant, adapter)
    assert adapter.calls == 1

    resolved = app.reconcile(
        summary.run_id,
        read_probe=lambda: ToolResult(value={"qty": 7}, evidence={"source": "read"}),
        conclude=lambda observed: ReconciliationResult(
            conclusion="applied",
            evidence=observed.evidence,
            message="target state already present",
        ),
        verify=lambda result: VerificationResult(
            passed=result.value.get("qty") == 7, message="verified after reconcile"
        ),
    )
    assert resolved.status == "completed"
    assert adapter.calls == 1
    assert resolved.verification_results[-1]["message"] == "verified after reconcile"


def test_reconciliation_not_applied_authorizes_exactly_one_retry():
    app = AutomationApplication(store=InMemoryEventStore())
    version, grant, adapter = setup_write(app, "timeout")
    first = execute(app, version, grant, adapter)
    assert first.status == "needs_reconciliation"

    cleared = app.reconcile(
        first.run_id,
        read_probe=lambda: ToolResult(value={"qty": 0}, evidence={"source": "read"}),
        conclude=lambda observed: ReconciliationResult(
            conclusion="not_applied",
            evidence=observed.evidence,
            message="write never landed",
        ),
    )
    assert cleared.status == "failed"
    assert cleared.failure_kind == "not_applied"

    adapter.behavior = "ok"
    second = execute(app, version, grant, adapter)
    assert second.status == "completed"
    assert adapter.calls == 2

    with pytest.raises(DuplicateWriteError):
        execute(app, version, grant, adapter)
    assert adapter.calls == 2


def test_still_unknown_remains_terminal_for_unattended_execution():
    app = AutomationApplication(store=InMemoryEventStore())
    version, grant, adapter = setup_write(app, "transport")
    summary = execute(app, version, grant, adapter)
    terminal = app.reconcile(
        summary.run_id,
        read_probe=lambda: ToolResult(evidence={"source": "read"}),
        conclude=lambda _observed: ReconciliationResult(
            conclusion="still_unknown",
            evidence={"probe": "inconclusive"},
            message="cannot prove either way",
        ),
    )
    assert terminal.status == "needs_reconciliation"
    assert terminal.next_required
    with pytest.raises(DuplicateWriteError):
        execute(app, version, grant, adapter)
    assert adapter.calls == 1


def test_reopen_and_replay_do_not_reinvoke_write_adapter(tmp_path):
    workspace = tmp_path / "ws"
    app = AutomationApplication(workspace)
    version, grant, adapter = setup_write(app, "ambiguous")
    summary = execute(app, version, grant, adapter)
    run_id = summary.run_id
    app.close()
    assert adapter.calls == 1

    reopened = AutomationApplication(workspace, read_only=True)
    try:
        again = reopened.inspect_run(run_id)
    finally:
        reopened.close()
    assert again.status == "needs_reconciliation"
    assert adapter.calls == 1

    writer = AutomationApplication(workspace)
    try:
        with pytest.raises(DuplicateWriteError):
            execute(writer, version, grant, adapter)
        assert adapter.calls == 1
    finally:
        writer.close()


def test_duplicate_command_delivery_is_deduplicated_by_scope():
    app = AutomationApplication(store=InMemoryEventStore())
    version, grant, adapter = setup_write(app, "ok")
    first = execute(app, version, grant, adapter)
    assert first.status == "completed"
    with pytest.raises(DuplicateWriteError):
        execute(app, version, grant, adapter)
    assert adapter.calls == 1
