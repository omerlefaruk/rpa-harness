"""Flagship ActiveGraph journey through the application interface (acceptance #35)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from harness.automation.capabilities import CapabilityExecutor, CapabilityOp, FakeBrowser
from harness.automation.credentials import CredentialService, InMemoryCredentialBackend
from harness.automation.scheduler import ScheduledTaskSpec, TaskSchedulerService
from harness.automation.workspace_runtime import WorkspaceRuntimeManager


def test_flagship_windows_workspace_journey(tmp_path: Path):
    workspace = tmp_path / "flagship"
    # Clean install of pinned workspace runtime
    status = WorkspaceRuntimeManager(workspace).initialize(release_source="test:flagship")
    assert status.active is not None
    assert status.active.product_version

    browser = FakeBrowser()
    executor = CapabilityExecutor(browser=browser)
    creds = CredentialService(InMemoryCredentialBackend())
    created = creds.create("form_token", "plain-secret", actor="operator")
    assert created["secret"] != "plain-secret"

    app = AutomationApplication(workspace)

    # Author + validate + register typed automation (read + write)
    read_proposal = AutomationProposal(
        proposal_id="flag-read",
        intent=AutomationIntent(
            intent_id="intent-read",
            name="Read inventory",
            objective="Extract count",
            required_capabilities=("browser",),
        ),
        discovery=DiscoveryEvidence(
            evidence_id="disc-read",
            selectors=(SelectorEvidence("role", "count", True),),
            observed_capabilities=("browser",),
        ),
        definition=AutomationDefinition(
            definition_id="flag-read",
            name="Read inventory",
            success_check="count present",
            actions=(
                AutomationAction(
                    "extract",
                    "browser",
                    "R0",
                    "count present",
                    selector=SelectorEvidence("role", "count", True),
                ),
            ),
        ),
    )
    assert app.validate_proposal(read_proposal).accepted
    read_version = app.register_proposal(read_proposal)

    write_proposal = AutomationProposal(
        proposal_id="flag-write",
        intent=AutomationIntent(
            intent_id="intent-write",
            name="Fill inventory",
            objective="Write qty",
            required_capabilities=("browser",),
        ),
        discovery=DiscoveryEvidence(
            evidence_id="disc-write",
            selectors=(SelectorEvidence("label", "Qty", True),),
            observed_capabilities=("browser",),
        ),
        definition=AutomationDefinition(
            definition_id="flag-write",
            name="Fill inventory",
            success_check="field filled",
            action_id="fill",
            action_class="R3",
            read_only=False,
            target_scope="warehouse-a",
            record_scope="sku-1",
            side_effect_scope="inventory.qty",
            idempotency_scope="flag-write:sku-1",
            credential_names=("form_token",),
            actions=(
                AutomationAction(
                    "fill",
                    "browser",
                    "R3",
                    "field filled",
                    selector=SelectorEvidence("label", "Qty", True),
                    credential_names=("form_token",),
                    inputs={"value": "${secrets.form_token}"},
                ),
            ),
        ),
    )
    write_version = app.register_proposal(write_proposal)
    grant = app.grant_approval(
        definition_id=write_version.definition.definition_id,
        version=write_version.version,
        actor="operator@example",
        target_scope="warehouse-a",
        record_scope="sku-1",
        side_effect_scope="inventory.qty",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        action_id="fill",
    )

    # Read path
    read_summary = app.execute_read_only(
        "flag-read",
        executor.as_read_adapter(
            CapabilityOp(
                "extract",
                "R0",
                True,
                selector=SelectorEvidence("role", "count", True),
            )
        ),
        lambda result: VerificationResult(
            passed="count" in str(result.value.get("text", "")),
            message="count present",
        ),
    )
    assert read_summary.status == "completed"
    assert read_summary.evidence_references

    # Approval-gated write with secret at edge only
    write_summary = app.execute_write(
        "flag-write",
        version=write_version.version,
        grant_id=grant.grant_id,
        adapter=executor.as_write_adapter(
            CapabilityOp(
                "fill",
                "R3",
                False,
                inputs={"value": "${secrets.form_token}"},
                selector=SelectorEvidence("label", "Qty", True),
            )
        ),
        verify=lambda result: VerificationResult(
            passed=result.value.get("filled") is True, message="filled"
        ),
        actor="operator@example",
        secret_adapter=MappingSecretAdapter(
            {"form_token": creds.resolve_edge("form_token").reveal()}
        ),
    )
    assert write_summary.status == "completed"
    assert "plain-secret" not in str(write_summary.to_dict())

    # Ambiguous write path → reconcile
    browser.unknown_write = True
    amb_def = AutomationDefinition(
        definition_id="flag-amb",
        name="Ambiguous fill",
        success_check="filled",
        action_id="fill",
        action_class="R3",
        read_only=False,
        target_scope="warehouse-a",
        record_scope="sku-2",
        side_effect_scope="inventory.qty",
        idempotency_scope="flag-amb:sku-2",
        actions=(
            AutomationAction(
                "fill",
                "browser",
                "R3",
                "filled",
                selector=SelectorEvidence("label", "Qty", True),
            ),
        ),
    )
    amb_version = app.register_proposal(
        AutomationProposal(
            proposal_id="flag-amb",
            intent=AutomationIntent(
                intent_id="intent-amb",
                name="Ambiguous",
                objective="write",
                required_capabilities=("browser",),
            ),
            discovery=DiscoveryEvidence(
                evidence_id="disc-amb",
                selectors=(SelectorEvidence("label", "Qty", True),),
                observed_capabilities=("browser",),
            ),
            definition=amb_def,
        )
    )
    amb_grant = app.grant_approval(
        definition_id=amb_version.definition.definition_id,
        version=amb_version.version,
        actor="operator@example",
        target_scope="warehouse-a",
        record_scope="sku-2",
        side_effect_scope="inventory.qty",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        action_id="fill",
    )
    amb = app.execute_write(
        "flag-amb",
        version=amb_version.version,
        grant_id=amb_grant.grant_id,
        adapter=executor.as_write_adapter(
            CapabilityOp(
                "fill",
                "R3",
                False,
                inputs={"value": "7"},
                selector=SelectorEvidence("label", "Qty", True),
            )
        ),
        verify=lambda result: VerificationResult(passed=True, message="ok"),
        actor="operator@example",
    )
    assert amb.status == "needs_reconciliation"
    reconciled = app.reconcile(
        amb.run_id,
        read_probe=lambda: ToolResult(value={"filled": True}, evidence={"src": "read"}),
        conclude=lambda observed: __import__(
            "harness.automation", fromlist=["ReconciliationResult"]
        ).ReconciliationResult(
            conclusion="applied", evidence=observed.evidence, message="present"
        ),
        verify=lambda result: VerificationResult(passed=True, message="verified"),
    )
    assert reconciled.status == "completed"

    # Selector repair trial + promote
    failed = app.execute_read_only(
        "flag-read",
        lambda _d, _r: ToolResult(value={}),
        lambda _r: VerificationResult(
            passed=False, message="selector failed", failure_kind="selector_failed"
        ),
    )
    repair = app.propose_repair(
        parent_definition_id=read_version.definition.definition_id,
        parent_version=read_version.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=DiscoveryEvidence(
            evidence_id="repair",
            selectors=(SelectorEvidence("role", "inventory count", True),),
            observed_capabilities=("browser",),
        ),
        proposed_definition=AutomationDefinition(
            definition_id="flag-read",
            name="Read inventory",
            success_check="count present",
            actions=(
                AutomationAction(
                    "extract",
                    "browser",
                    "R0",
                    "count present",
                    selector=SelectorEvidence("role", "inventory count", True),
                ),
            ),
        ),
    )
    trial = app.trial_repair(
        repair.repair_id,
        adapter=lambda _d, _r: ToolResult(value={"text": "count:9"}),
        verify=lambda result: VerificationResult(passed=True, message="ok"),
    )
    promoted = app.promote_repair(repair.repair_id, trial_id=trial.trial_id)
    assert promoted.version == 2
    assert len(app.definition_versions("flag-read")) == 2

    # Task Scheduler pinned registration (unattended path through same interface identity)
    sched = TaskSchedulerService(workspace)
    record = sched.register(
        ScheduledTaskSpec(
            task_name="flagship-nightly",
            workspace=str(workspace),
            runtime_version=status.active.product_version,
            definition_id="flag-write",
            definition_version=write_version.version,
            target_scope="warehouse-a",
            trigger="daily",
        )
    )
    runtime_version = record.spec.runtime_version
    launch = sched.validate_launch(
        "flagship-nightly",
        runtime_version=runtime_version,
        credentials_present=True,
        workspace_locked=False,
    )
    assert launch["ok"] is True
    assert "secret" not in " ".join(launch["cli_args"]).lower()
    sched.mark_launch("flagship-nightly", run_id=write_summary.run_id, status="completed")

    # Rollback workspace runtime demonstration
    manager = WorkspaceRuntimeManager(workspace)
    upgraded = manager.upgrade(
        __import__(
            "harness.automation.workspace_runtime", fromlist=["default_manifest"]
        ).default_manifest(
            product_version="9.9.9",
            release_source="test:upgrade",
        )
    )
    assert upgraded
    rolled = manager.rollback()
    assert rolled

    app.close()
    # Read-only reopen does not re-invoke writes
    inspector = AutomationApplication(workspace, read_only=True)
    try:
        assert inspector.inspect_run(write_summary.run_id).status == "completed"
    finally:
        inspector.close()
    assert len(browser.writes) >= 1
