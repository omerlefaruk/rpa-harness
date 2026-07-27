"""Approval-gated write execution through the automation application seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    ApprovalError,
    AuthorityError,
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    DuplicateWriteError,
    MappingSecretAdapter,
    SelectorEvidence,
    ToolResult,
    VerificationResult,
)
from harness.security import REDACTED, SecretValue


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
                selector=SelectorEvidence("role", "save", True),
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
    def __init__(self, result: ToolResult | None = None, error: Exception | None = None):
        self.result = result or ToolResult(
            value={"qty": 7},
            evidence={"password": "super-secret", "status": "written"},
        )
        self.error = error
        self.calls: list[dict] = []

    def __call__(self, definition, run_id, *, secrets, action):
        self.calls.append(
            {
                "definition_id": definition.definition_id,
                "run_id": run_id,
                "secret_names": sorted(secrets),
                "secret_types": {name: type(value).__name__ for name, value in secrets.items()},
                "revealed": {name: value.reveal() for name, value in secrets.items()},
                "action_id": None if action is None else action.action_id,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


def register_write(app: AutomationApplication, definition=None):
    return app.register_proposal(write_proposal(definition))


def grant_for(app: AutomationApplication, version, **changes):
    values = {
        "definition_id": version.definition.definition_id,
        "version": version.version,
        "actor": "operator@example",
        "target_scope": version.definition.target_scope,
        "record_scope": version.definition.record_scope,
        "side_effect_scope": version.definition.side_effect_scope,
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "action_id": version.definition.action_id,
        "governance_gate": version.definition.action_class == "R4",
    }
    values.update(changes)
    return app.grant_approval(**values)


def test_execute_write_requires_attempt_before_io_and_redacts_evidence(tmp_path):
    workspace = tmp_path / "ws"
    app = AutomationApplication(workspace)
    version = register_write(app)
    grant = grant_for(app, version)
    adapter = RecordingWriteAdapter()

    summary = app.execute_write(
        version.definition.definition_id,
        version=version.version,
        grant_id=grant.grant_id,
        adapter=adapter,
        verify=lambda result: VerificationResult(
            passed=result.value.get("qty") == 7,
            message="qty matches",
            evidence={"token": "should-redact", "ok": True},
        ),
        actor="operator@example",
        secret_adapter=MappingSecretAdapter({"api_token": "super-secret"}),
    )
    app.close()

    assert summary.status == "completed"
    assert summary.grant_id == grant.grant_id
    assert summary.definition_version == 1
    assert len(summary.evidence_references) == 1
    assert len(adapter.calls) == 1
    assert adapter.calls[0]["secret_names"] == ["api_token"]
    assert adapter.calls[0]["secret_types"] == {"api_token": "SecretValue"}
    assert adapter.calls[0]["revealed"] == {"api_token": "super-secret"}

    payload = summary.to_dict()
    assert "super-secret" not in str(payload)
    assert payload["verification_results"][0]["message"] == "qty matches"

    evidence_text = (workspace / summary.evidence_references[0].uri).read_text(encoding="utf-8")
    assert "super-secret" not in evidence_text
    assert REDACTED in evidence_text or "password" in evidence_text

    # Re-open read-only and ensure events never stored plaintext secrets.
    inspector = AutomationApplication(workspace, read_only=True)
    try:
        again = inspector.inspect_run(summary.run_id).to_dict()
    finally:
        inspector.close()
    assert "super-secret" not in str(again)
    assert again["status"] == "completed"


def test_missing_and_invalid_action_classes_fail_closed():
    app = AutomationApplication(store=InMemoryEventStore())

    with pytest.raises(AuthorityError, match="invalid action class"):
        app.register_definition(
            AutomationDefinition(
                definition_id="bad",
                name="Bad",
                success_check="x",
                action_class="R9",
                read_only=False,
            )
        )

    with pytest.raises(AuthorityError, match="invalid action class"):
        app.register_definition(
            AutomationDefinition(
                definition_id="bad2",
                name="Bad",
                success_check="x",
                action_class="R0",
                read_only=False,
            )
        )


def test_r3_requires_approval_and_r4_requires_governance_gate():
    app = AutomationApplication(store=InMemoryEventStore())
    version = register_write(app)
    adapter = RecordingWriteAdapter()

    with pytest.raises(ApprovalError):
        app.execute_write(
            version.definition.definition_id,
            version=version.version,
            grant_id="missing",
            adapter=adapter,
            verify=lambda _result: VerificationResult(passed=True),
            actor="operator@example",
            secret_adapter=MappingSecretAdapter({"api_token": "x"}),
        )

    r4 = register_write(
        app,
        write_definition(
            definition_id="inventory-write-r4",
            action_class="R4",
            actions=(
                AutomationAction(
                    action_id="update-inventory",
                    capability="write",
                    action_class="R4",
                    success_check="inventory count equals target",
                    credential_names=("api_token",),
                    inputs={"password": "${secrets.api_token}"},
                ),
            ),
        ),
    )
    with pytest.raises(AuthorityError, match="governance gate"):
        app.grant_approval(
            definition_id=r4.definition.definition_id,
            version=r4.version,
            actor="operator@example",
            target_scope=r4.definition.target_scope,
            record_scope=r4.definition.record_scope,
            side_effect_scope=r4.definition.side_effect_scope,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            governance_gate=False,
        )


@pytest.mark.parametrize(
    ("grant_changes", "execute_changes", "match"),
    [
        ({"actor": "other@example"}, {}, "actor"),
        ({"target_scope": "warehouse-b"}, {}, "target"),
        ({"record_scope": "sku-2"}, {}, "record"),
        ({"side_effect_scope": "other"}, {}, "side-effect"),
        ({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, {}, "expired"),
        ({}, {"version": 99}, "Unknown definition version"),
    ],
)
def test_stale_expired_and_mismatched_approvals_are_rejected(
    grant_changes, execute_changes, match
):
    app = AutomationApplication(store=InMemoryEventStore())
    version = register_write(app)
    if "version" in execute_changes:
        grant = grant_for(app, version)
        with pytest.raises((ApprovalError, KeyError), match=match):
            app.execute_write(
                version.definition.definition_id,
                version=execute_changes["version"],
                grant_id=grant.grant_id,
                adapter=RecordingWriteAdapter(),
                verify=lambda _result: VerificationResult(passed=True),
                actor="operator@example",
                secret_adapter=MappingSecretAdapter({"api_token": "x"}),
            )
        return

    grant = grant_for(app, version, **grant_changes)
    with pytest.raises(ApprovalError, match=match):
        app.execute_write(
            version.definition.definition_id,
            version=version.version,
            grant_id=grant.grant_id,
            adapter=RecordingWriteAdapter(),
            verify=lambda _result: VerificationResult(passed=True),
            actor="operator@example",
            secret_adapter=MappingSecretAdapter({"api_token": "x"}),
            now=datetime.now(UTC),
        )


def test_secret_adapter_never_returns_plaintext_to_agent_surface():
    adapter = MappingSecretAdapter({"api_token": "super-secret"})
    secret = adapter.resolve("${secrets.api_token}")
    assert isinstance(secret, SecretValue)
    assert str(secret) == REDACTED
    assert repr(secret) == REDACTED
    assert secret.reveal() == "super-secret"


def test_write_runs_at_most_once_for_idempotency_scope():
    app = AutomationApplication(store=InMemoryEventStore())
    version = register_write(app)
    grant = grant_for(app, version)
    adapter = RecordingWriteAdapter()
    secrets = MappingSecretAdapter({"api_token": "x"})

    first = app.execute_write(
        version.definition.definition_id,
        version=version.version,
        grant_id=grant.grant_id,
        adapter=adapter,
        verify=lambda _result: VerificationResult(passed=True, message="ok"),
        actor="operator@example",
        secret_adapter=secrets,
    )
    assert first.status == "completed"
    assert len(adapter.calls) == 1

    with pytest.raises(DuplicateWriteError, match="already admitted"):
        app.execute_write(
            version.definition.definition_id,
            version=version.version,
            grant_id=grant.grant_id,
            adapter=adapter,
            verify=lambda _result: VerificationResult(passed=True, message="ok"),
            actor="operator@example",
            secret_adapter=secrets,
        )
    assert len(adapter.calls) == 1


def test_completion_requires_verification_result_and_evidence_reference():
    app = AutomationApplication(store=InMemoryEventStore())
    version = register_write(app)
    grant = grant_for(app, version)

    failed = app.execute_write(
        version.definition.definition_id,
        version=version.version,
        grant_id=grant.grant_id,
        adapter=RecordingWriteAdapter(result=ToolResult(value={"qty": 1})),
        verify=lambda result: VerificationResult(
            passed=False,
            message="qty mismatch",
            failure_kind="verification_failed",
            evidence={"expected": 7, "actual": result.value.get("qty")},
        ),
        actor="operator@example",
        secret_adapter=MappingSecretAdapter({"api_token": "x"}),
    )

    assert failed.status == "failed"
    assert failed.failure_kind == "verification_failed"
    assert failed.verification_results
    assert failed.evidence_references


def test_content_hash_mismatch_rejects_stale_grant_after_new_version():
    app = AutomationApplication(store=InMemoryEventStore())
    first = register_write(app)
    grant = grant_for(app, first)
    second = register_write(
        app,
        write_definition(
            success_check="inventory count equals target and audit",
            actions=(
                AutomationAction(
                    action_id="update-inventory",
                    capability="write",
                    action_class="R3",
                    success_check="inventory count equals target and audit",
                    credential_names=("api_token",),
                    inputs={"password": "${secrets.api_token}", "qty": 8},
                ),
            ),
        ),
    )
    assert second.version == 2
    assert second.content_hash != first.content_hash

    with pytest.raises(ApprovalError, match="version"):
        app.execute_write(
            first.definition.definition_id,
            version=second.version,
            grant_id=grant.grant_id,
            adapter=RecordingWriteAdapter(),
            verify=lambda _result: VerificationResult(passed=True),
            actor="operator@example",
            secret_adapter=MappingSecretAdapter({"api_token": "x"}),
        )
