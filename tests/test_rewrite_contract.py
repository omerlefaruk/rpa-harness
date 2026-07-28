from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AutomationApplication,
    EvidenceStore,
    Principal,
    SourceValidationError,
    ToolResult,
    VerificationResult,
    discover_skills,
    validate_source,
)
from harness.automation.credentials import CredentialService, InMemoryCredentialBackend
from harness.mcp_server import handle_request


def test_source_validation_fails_closed_for_direct_effects_and_unpinned_deps():
    validation = validate_source(
        "from pathlib import Path\nPath('x').write_text('bad')\n",
        dependency_lock="httpx>=0.1",
        declared_action_class="R0",
    )
    assert not validation.accepted
    assert any("outside an Action Boundary" in error for error in validation.errors)
    assert any("unpinned dependency" in error for error in validation.errors)


def test_source_snapshot_is_immutable_and_worker_uses_snapshot(tmp_path):
    app = AutomationApplication(tmp_path / "workspace")
    version = app.register_source(
        definition_id="snapshot-read",
        name="Snapshot read",
        success_check="result is present",
        source="def main(payload):\n    return {'value': payload['value']}\n",
    )
    assert version.definition.source_hash
    response = app.run_snapshot(
        next(path for path in (tmp_path / "workspace" / "snapshots").glob("*.py")),
        request_id="req-1",
        payload={"value": 3},
    )
    assert response.ok is True
    assert response.value == {"value": 3}
    app.close()


def test_agent_principal_cannot_grant_or_write(tmp_path):
    app = AutomationApplication(tmp_path / "workspace")
    with pytest.raises(PermissionError, match="operator"):
        app.grant_approval(
            definition_id="missing",
            version=1,
            actor="agent",
            target_scope="",
            record_scope="",
            side_effect_scope="",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            principal=Principal("agent", "model"),
        )
    credentials = CredentialService(InMemoryCredentialBackend())
    with pytest.raises(PermissionError):
        credentials.create("token", "secret", actor="model", principal=Principal("agent", "model"))
    app.close()


def test_graph_queries_and_content_addressed_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    app = AutomationApplication(workspace)
    from harness.automation import AutomationDefinition

    app.register_definition(AutomationDefinition("read", "Read", "value is present"))
    assert app.graph_automations()[0]["definition_id"] == "read"
    summary = app.execute_read_only(
        "read",
        lambda _definition, _run_id: ToolResult(value={"value": 1}, evidence={"same": True}),
        lambda result: VerificationResult(passed=bool(result.value.get("value"))),
    )
    path = workspace / summary.evidence_references[0].uri
    assert path.exists()
    assert summary.evidence_references[0].content_hash in path.name
    app.close()
    reopened = AutomationApplication(workspace, read_only=True)
    assert reopened.graph_automations()[0]["definition_id"] == "read"
    assert reopened.inspect_run(summary.run_id).status == "completed"
    reopened.close()


def test_python_mcp_exposes_skills_and_no_operator_grant_tool():
    initialized = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["serverInfo"]["name"] == "rpa-harness"
    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {item["name"] for item in listed["result"]["tools"]}
    assert "list_feature_skills" in names
    assert "grant_approval" not in names
    assert discover_skills()
