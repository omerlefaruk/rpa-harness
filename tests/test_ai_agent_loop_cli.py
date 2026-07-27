"""Full AI agent loop through CLI adapters (same path MCP uses).

Simulates: AI writes JSON → CLI → AutomationApplication → ActiveGraph EventStore.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, payload: dict) -> str:
    # MCP requires relative paths; tests use names relative to cwd via str(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def test_ai_agent_loop_via_cli_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workspace = Path("ws")
    init = cli("--automation-init-workspace", str(workspace))
    assert init.returncode == 0, init.stderr

    # AI drafts a write proposal JSON
    proposal = {
        "proposal_id": "ai-prop-1",
        "schema_version": "v1",
        "intent": {
            "intent_id": "intent-1",
            "name": "Update qty",
            "objective": "Set inventory qty",
            "required_capabilities": ["write"],
            "unresolved_business_ambiguities": [],
            "schema_version": "v1",
        },
        "discovery": {
            "evidence_id": "disc-1",
            "selectors": [{"strategy": "role", "locator": "Save", "verified": True}],
            "observed_capabilities": ["write"],
            "schema_version": "v1",
        },
        "definition": {
            "definition_id": "ai-write",
            "name": "Update qty",
            "success_check": "qty equals 7",
            "action_id": "update-qty",
            "action_class": "R3",
            "read_only": False,
            "target_scope": "warehouse-a",
            "record_scope": "sku-1",
            "side_effect_scope": "inventory.qty",
            "idempotency_scope": "ai-write:sku-1",
            "credential_names": ["api_token"],
            "actions": [
                {
                    "action_id": "update-qty",
                    "capability": "write",
                    "action_class": "R3",
                    "success_check": "qty equals 7",
                    "selector": {"strategy": "role", "locator": "Save", "verified": True},
                    "credential_names": ["api_token"],
                    "inputs": {"password": "${secrets.api_token}", "qty": 7},
                }
            ],
            "schema_version": "v1",
        },
    }
    proposal_path = write_json(Path("proposal.json"), proposal)

    validated = cli("--automation-validate-proposal", proposal_path)
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["accepted"] is True

    # Optional propose admission (agent as model)
    propose_req = write_json(Path("propose.json"), {"proposal": proposal})
    proposed = cli(
        "--automation-propose",
        propose_req,
        "--automation-workspace",
        str(workspace),
    )
    assert proposed.returncode == 0, proposed.stderr

    registered = cli(
        "--automation-register-proposal",
        proposal_path,
        "--automation-workspace",
        str(workspace),
    )
    assert registered.returncode == 0, registered.stderr
    version = json.loads(registered.stdout)
    assert version["version"] == 1

    grant_path = write_json(
        Path("grant.json"),
        {
            "definition_id": "ai-write",
            "version": 1,
            "actor": "operator@example",
            "target_scope": "warehouse-a",
            "record_scope": "sku-1",
            "side_effect_scope": "inventory.qty",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "action_id": "update-qty",
        },
    )
    granted = cli(
        "--automation-grant-approval",
        grant_path,
        "--automation-workspace",
        str(workspace),
    )
    assert granted.returncode == 0, granted.stderr
    grant = json.loads(granted.stdout)

    exec_req = write_json(
        Path("execute_write.json"),
        {
            "definition_id": "ai-write",
            "version": 1,
            "grant_id": grant["grant_id"],
            "actor": "operator@example",
            "port": "fake_browser",
            "op": {
                "name": "fill",
                "action_class": "R3",
                "read_only": False,
                "inputs": {"value": "${secrets.api_token}"},
                "selector": {"strategy": "role", "locator": "Save", "verified": True},
            },
            "secrets": {"api_token": "edge-secret"},
        },
    )
    executed = cli(
        "--automation-execute-write",
        exec_req,
        "--automation-workspace",
        str(workspace),
    )
    assert executed.returncode == 0, executed.stderr
    summary = json.loads(executed.stdout)
    assert summary["status"] == "completed"
    assert "edge-secret" not in executed.stdout

    inspected = cli(
        "--automation-inspect",
        summary["run_id"],
        "--automation-workspace",
        str(workspace),
    )
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["status"] == "completed"

    # Unknown write → reconcile path
    amb_proposal = json.loads(json.dumps(proposal))
    amb_proposal["proposal_id"] = "ai-prop-amb"
    amb_proposal["definition"]["definition_id"] = "ai-amb"
    amb_proposal["definition"]["idempotency_scope"] = "ai-amb:sku-1"
    amb_proposal["definition"]["record_scope"] = "sku-amb"
    amb_path = write_json(Path("proposal_amb.json"), amb_proposal)
    reg2 = cli(
        "--automation-register-proposal",
        amb_path,
        "--automation-workspace",
        str(workspace),
    )
    assert reg2.returncode == 0, reg2.stderr
    grant2_path = write_json(
        Path("grant2.json"),
        {
            "definition_id": "ai-amb",
            "version": 1,
            "actor": "operator@example",
            "target_scope": "warehouse-a",
            "record_scope": "sku-amb",
            "side_effect_scope": "inventory.qty",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "action_id": "update-qty",
        },
    )
    g2 = json.loads(
        cli(
            "--automation-grant-approval",
            grant2_path,
            "--automation-workspace",
            str(workspace),
        ).stdout
    )
    amb_exec = write_json(
        Path("execute_amb.json"),
        {
            "definition_id": "ai-amb",
            "version": 1,
            "grant_id": g2["grant_id"],
            "actor": "operator@example",
            "op": {
                "name": "fill",
                "action_class": "R3",
                "read_only": False,
                "inputs": {"value": "7"},
                "selector": {"strategy": "role", "locator": "Save", "verified": True},
            },
            "secrets": {"api_token": "edge-secret"},
            "fixture_result": {
                "value": {},
                "evidence": {"stage": "timeout"},
                "write_outcome": "unknown",
            },
        },
    )
    amb_run = cli(
        "--automation-execute-write",
        amb_exec,
        "--automation-workspace",
        str(workspace),
    )
    assert amb_run.returncode == 0, amb_run.stderr or amb_run.stdout
    amb_summary = json.loads(amb_run.stdout)
    assert amb_summary["status"] == "needs_reconciliation"

    recon = write_json(
        Path("reconcile.json"),
        {
            "run_id": amb_summary["run_id"],
            "conclusion": "applied",
            "observed_value": {"filled": True, "qty": 7},
            "evidence": {"source": "read_probe"},
            "message": "state already applied",
        },
    )
    recon_out = cli(
        "--automation-reconcile",
        recon,
        "--automation-workspace",
        str(workspace),
    )
    assert recon_out.returncode == 0, recon_out.stderr
    assert json.loads(recon_out.stdout)["status"] == "completed"
