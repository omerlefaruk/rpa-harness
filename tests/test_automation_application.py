import json
import subprocess
import sys

import pytest
from activegraph import Graph, Runtime
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AutomationApplication,
    AutomationDefinition,
    ToolResult,
    VerificationResult,
    WorkspaceRuntimeActiveError,
)
from harness.automation.pack import pack


def definition():
    return AutomationDefinition(
        definition_id="inventory-read",
        name="Read inventory",
        success_check="inventory count is present",
    )


def passed(result):
    return VerificationResult(passed="count" in result.value, message="count returned")


@pytest.mark.parametrize("store_factory", [InMemoryEventStore])
def test_application_completes_verified_read_only_run_in_memory(store_factory):
    app = AutomationApplication(store=store_factory())
    app.register_definition(definition())

    summary = app.execute_read_only(
        "inventory-read",
        lambda _definition, _run_id: ToolResult(value={"count": 3}),
        passed,
    )

    assert summary.status == "completed"
    assert summary.verification_results == (
        {"passed": True, "message": "count returned", "failure_kind": None},
    )
    assert len(summary.evidence_references) == 1
    assert app.inspect_run(summary.run_id).to_dict() == summary.to_dict()


def test_application_uses_sqlite_events_for_cli_and_failure_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    app = AutomationApplication(workspace)
    app.register_definition(definition())

    summary = app.execute_read_only(
        "inventory-read",
        lambda _definition, _run_id: ToolResult(evidence={"source": "fixture"}),
        lambda _result: VerificationResult(
            passed=False,
            message="count missing",
            failure_kind="verification_failed",
            evidence={"expected": "count"},
        ),
    )
    app.close()

    assert summary.status == "failed"
    assert summary.failure_kind == "verification_failed"
    assert (workspace / summary.evidence_references[0].uri).exists()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--automation-inspect",
            summary.run_id,
            "--automation-workspace",
            str(workspace),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == summary.to_dict()


def test_workspace_allows_read_only_inspection_but_not_second_writer(tmp_path):
    workspace = tmp_path / "workspace"
    writer = AutomationApplication(workspace)

    with pytest.raises(WorkspaceRuntimeActiveError):
        AutomationApplication(workspace)

    inspector = AutomationApplication(workspace, read_only=True)
    inspector.close()
    writer.close()


def test_definition_requires_explicit_read_only_success_check():
    app = AutomationApplication(store=InMemoryEventStore())

    with pytest.raises(ValueError, match="explicit success check"):
        app.register_definition(
            AutomationDefinition(
                definition_id="invalid",
                name="Invalid",
                success_check="",
            )
        )


def test_first_party_pack_declares_the_read_only_lifecycle_surface():
    runtime = Runtime(Graph(), store=InMemoryEventStore())
    runtime.load_pack(pack)

    assert {item.name for item in pack.object_types} >= {
        "automation_definition",
        "run",
        "action_attempt",
        "verification_result",
        "evidence_reference",
    }
    assert [item.name for item in pack.tools] == ["read_only_action"]
    assert [item.name for item in pack.behaviors] == ["start_read_only_run"]
