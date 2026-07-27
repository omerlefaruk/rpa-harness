"""Contract tests for the ActiveGraph automation-application interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.activegraph_app.application import ApplicationError, AutomationApplication
from harness.activegraph_app.workspace import WorkspaceLockError, WorkspaceWriteLock


def _app(tmp_path: Path, **kwargs) -> AutomationApplication:
    app = AutomationApplication(tmp_path, **kwargs)
    app.init_workspace()
    return app


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_readonly_run_completes_with_verification_and_evidence(tmp_path: Path, store_kind: str) -> None:
    calls: list[str] = []

    def probe(target: str) -> dict:
        calls.append(target)
        return {
            "value": "ok-value",
            "observed_at": "2026-07-27T00:00:00+00:00",
            "redacted_snippet": "value=ok-value",
        }

    app = _app(tmp_path / store_kind, store_kind=store_kind, read_probe=probe)
    definition = app.register_readonly_definition(
        name="probe-target",
        target="inventory-status",
        success_check="equals",
        expected_value="ok-value",
        definition_id="def_probe",
    )
    assert definition.content_hash
    assert definition.definition_id == "def_probe"

    summary = app.execute_readonly_run(definition_id="def_probe", run_id="run_1")
    assert summary.status == "completed"
    assert summary.failure_kind is None
    assert len(summary.attempts) == 1
    attempt = summary.attempts[0]
    assert attempt.status == "succeeded"
    assert attempt.verification is not None
    assert attempt.verification.passed is True
    assert attempt.evidence
    assert attempt.evidence[0].redacted is True
    assert calls == ["inventory-status"]

    inspected = app.inspect_run("run_1")
    assert inspected.status == summary.status
    assert inspected.run_id == summary.run_id
    assert inspected.attempts == summary.attempts
    assert inspected.failure_kind == summary.failure_kind

    evidence_path = tmp_path / store_kind / attempt.evidence[0].path
    assert evidence_path.is_file()
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["redacted"] is True


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_failed_verification_marks_run_failed(tmp_path: Path, store_kind: str) -> None:
    def probe(target: str) -> dict:
        return {
            "value": "wrong",
            "observed_at": "2026-07-27T00:00:00+00:00",
            "redacted_snippet": "value=wrong",
        }

    app = _app(tmp_path / store_kind, store_kind=store_kind, read_probe=probe)
    app.register_readonly_definition(
        name="probe-target",
        target="x",
        success_check="equals",
        expected_value="expected",
        definition_id="def_fail",
    )
    summary = app.execute_readonly_run(definition_id="def_fail", run_id="run_fail")
    assert summary.status == "failed"
    assert summary.failure_kind == "verification_mismatch"
    assert summary.attempts[0].verification is not None
    assert summary.attempts[0].verification.passed is False
    assert summary.attempts[0].status == "failed"


def test_workspace_write_lock_blocks_second_writer(tmp_path: Path) -> None:
    app = _app(tmp_path, store_kind="sqlite")
    with WorkspaceWriteLock(tmp_path, owner="first"):
        with pytest.raises(WorkspaceLockError):
            with WorkspaceWriteLock(tmp_path, owner="second"):
                pass
    # After release, write path works again.
    app.register_readonly_definition(
        name="after-lock",
        target="t",
        success_check="exists",
        definition_id="def_lock",
    )


def test_init_workspace_is_idempotent(tmp_path: Path) -> None:
    app = AutomationApplication(tmp_path)
    first = app.init_workspace()
    marker = tmp_path / "definitions" / "operator.json"
    marker.write_text('{"keep": true}\n', encoding="utf-8")
    second = app.init_workspace()
    assert first.to_dict() == second.to_dict()
    assert marker.read_text(encoding="utf-8") == '{"keep": true}\n'


def test_missing_success_check_rejected(tmp_path: Path) -> None:
    app = _app(tmp_path, store_kind="memory")
    with pytest.raises(ApplicationError):
        app.register_readonly_definition(
            name="bad",
            target="t",
            success_check="   ",
        )
