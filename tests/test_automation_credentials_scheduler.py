"""Credential handle-only surface and pinned Task Scheduler registrations."""

from __future__ import annotations

from harness.automation.credentials import CredentialService, InMemoryCredentialBackend
from harness.automation.scheduler import ScheduledTaskSpec, TaskSchedulerService
from harness.security import REDACTED, SecretValue


def test_credential_lifecycle_is_handle_only_and_audited():
    backend = InMemoryCredentialBackend()
    service = CredentialService(backend)
    created = service.create("api_token", "super-secret", actor="operator")
    assert created["secret"] == REDACTED
    assert created["handle"].startswith("cred://")
    assert "super-secret" not in str(created)

    resolved = service.resolve_handle(created["handle"], actor="operator")
    assert resolved["secret"] == REDACTED
    assert resolved["name"] == "api_token"

    edge = service.resolve_edge(created["handle"])
    assert isinstance(edge, SecretValue)
    assert edge.reveal() == "super-secret"
    assert str(edge) == REDACTED

    rotated = service.rotate("api_token", "new-secret", actor="operator")
    assert rotated["secret"] == REDACTED
    assert service.resolve_edge("api_token").reveal() == "new-secret"

    service.delete("api_token", actor="operator")
    assert all(item.action_class == "R3" for item in service.audit)
    assert {item.operation for item in service.audit} >= {
        "create",
        "resolve",
        "rotate",
        "delete",
    }
    assert all("super-secret" not in str(item.to_dict()) for item in service.audit)


def test_scheduler_registration_is_idempotent_and_secret_free(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    scheduler = TaskSchedulerService(workspace)
    spec = ScheduledTaskSpec(
        task_name="nightly-inventory",
        workspace=str(workspace),
        runtime_version="1.0.0",
        definition_id="inventory-write",
        definition_version=2,
        target_scope="warehouse-a",
        trigger="daily-02:00",
    )
    first = scheduler.register(spec)
    second = scheduler.register(spec)
    assert first.registration_id == second.registration_id
    args = " ".join(first.spec.cli_args())
    assert "secret" not in args.lower()
    assert "--automation-execute-version" in first.spec.cli_args()
    assert "inventory-write@2" in first.spec.cli_args()

    ok = scheduler.validate_launch(
        "nightly-inventory",
        runtime_version="1.0.0",
        credentials_present=True,
        workspace_locked=False,
    )
    assert ok["ok"] is True

    for error_case, kwargs in [
        ("disabled", {"enabled": False}),
    ]:
        del error_case
    scheduler.disable("nightly-inventory")
    assert scheduler.validate_launch(
        "nightly-inventory",
        runtime_version="1.0.0",
        credentials_present=True,
        workspace_locked=False,
    ) == {"ok": False, "error": "disabled"}

    scheduler.register(spec)
    assert (
        scheduler.validate_launch(
            "nightly-inventory",
            runtime_version="1.0.0",
            credentials_present=False,
            workspace_locked=False,
        )["error"]
        == "missing-credential"
    )
    assert (
        scheduler.validate_launch(
            "nightly-inventory",
            runtime_version="1.0.0",
            credentials_present=True,
            workspace_locked=True,
        )["error"]
        == "locked-workspace"
    )
    assert (
        scheduler.validate_launch(
            "nightly-inventory",
            runtime_version="1.0.0",
            credentials_present=True,
            workspace_locked=False,
            approval_expired=True,
        )["error"]
        == "expired"
    )
    assert (
        scheduler.validate_launch(
            "nightly-inventory",
            runtime_version="0.9.0",
            credentials_present=True,
            workspace_locked=False,
        )["error"]
        == "runtime-mismatch-rollback-required"
    )

    launched = scheduler.mark_launch(
        "nightly-inventory", run_id="run_abc", status="completed"
    )
    assert launched.last_run_id == "run_abc"
    payload = launched.to_dict()
    assert payload["last_run_id"] == "run_abc"
