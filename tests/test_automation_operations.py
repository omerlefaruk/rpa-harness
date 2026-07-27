"""MCP/CLI operation catalog and adapter parity through the application interface."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from harness.automation import (
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    SelectorEvidence,
)
from harness.automation.operations import (
    CATALOG_VERSION,
    FORBIDDEN_MCP_TOOLS,
    list_operations,
    operation_contract,
)


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_operation_catalog_is_versioned_and_forbids_escape_hatches():
    ops = {item.name: item for item in list_operations()}
    assert CATALOG_VERSION == "v1"
    assert "validate_proposal" in ops
    assert "register_proposal" in ops
    assert "grant_approval" in ops
    assert "inspect_run" in ops
    assert "export_evidence" in ops
    for name in FORBIDDEN_MCP_TOOLS:
        assert name not in ops
    contract = operation_contract("grant_approval")
    assert contract.version == "v1"
    assert "actor" in contract.inputs
    assert contract.authorization == "approver"


def test_cli_list_operations_and_grant_export_parity(tmp_path: Path):
    listed = _cli("--automation-list-operations")
    assert listed.returncode == 0, listed.stderr
    payload = json.loads(listed.stdout)
    assert payload["catalog_version"] == "v1"
    assert any(item["name"] == "inspect_run" for item in payload["operations"])

    workspace = tmp_path / "ws"
    app = AutomationApplication(workspace)
    proposal = AutomationProposal(
        proposal_id="p1",
        intent=AutomationIntent(
            intent_id="i1",
            name="Read",
            objective="read count",
            required_capabilities=("read",),
        ),
        discovery=DiscoveryEvidence(
            evidence_id="d1",
            selectors=(SelectorEvidence("role", "count", True),),
            observed_capabilities=("read",),
        ),
        definition=AutomationDefinition(
            definition_id="inventory-read",
            name="Read",
            success_check="count present",
            actions=(
                AutomationAction(
                    "read-inventory",
                    "read",
                    "R0",
                    "count present",
                    selector=SelectorEvidence("role", "count", True),
                ),
            ),
        ),
    )
    version = app.register_proposal(proposal)
    # seed a completed run for export
    summary = app.execute_read_only(
        "inventory-read",
        lambda _d, _r: __import__(
            "harness.automation", fromlist=["ToolResult"]
        ).ToolResult(value={"count": 1}),
        lambda result: __import__(
            "harness.automation", fromlist=["VerificationResult"]
        ).VerificationResult(passed="count" in result.value, message="ok"),
    )
    app.close()

    grant_path = tmp_path / "grant.json"
    grant_path.write_text(
        json.dumps(
            {
                "definition_id": version.definition.definition_id,
                "version": version.version,
                "actor": "operator@example",
                "target_scope": "local",
                "record_scope": "r1",
                "side_effect_scope": "none",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "action_id": "read-inventory",
            }
        ),
        encoding="utf-8",
    )
    # grant on read-only R0 should still work for non-write scopes
    granted = _cli(
        "--automation-grant-approval",
        str(grant_path),
        "--automation-workspace",
        str(workspace),
    )
    # R0 grant may fail authority if write scopes required only for R3/R4 - should succeed
    assert granted.returncode == 0, granted.stderr
    assert json.loads(granted.stdout)["grant_id"]

    exported = _cli(
        "--automation-export-evidence",
        summary.run_id,
        "--automation-workspace",
        str(workspace),
    )
    assert exported.returncode == 0, exported.stderr
    body = json.loads(exported.stdout)
    assert body["run_id"] == summary.run_id
    assert body["evidence_references"]

    inspected = _cli(
        "--automation-inspect",
        summary.run_id,
        "--automation-workspace",
        str(workspace),
    )
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["status"] == "completed"
