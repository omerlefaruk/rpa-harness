"""CLI adapter contract tests for ActiveGraph commands."""

from __future__ import annotations

import json
from pathlib import Path

from harness.activegraph_app.cli_adapter import run_ag_cli


def test_cli_init_register_run_inspect_roundtrip(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "ws"
    assert run_ag_cli(["init-workspace", str(workspace)]) == 0
    init_out = json.loads(capsys.readouterr().out)
    assert init_out["activegraph_version"] == "1.10.0"
    assert (workspace / "workspace_manifest.json").is_file()

    assert (
        run_ag_cli(
            [
                "register-definition",
                str(workspace),
                "--name",
                "cli-probe",
                "--target",
                "status",
                "--success-check",
                "exists",
                "--definition-id",
                "def_cli",
            ]
        )
        == 0
    )
    reg = json.loads(capsys.readouterr().out)
    assert reg["definition_id"] == "def_cli"
    assert reg["content_hash"]

    assert (
        run_ag_cli(
            [
                "run",
                str(workspace),
                "--definition-id",
                "def_cli",
                "--run-id",
                "run_cli",
            ]
        )
        == 0
    )
    run_summary = json.loads(capsys.readouterr().out)
    assert run_summary["status"] == "completed"
    assert run_summary["run_id"] == "run_cli"

    assert run_ag_cli(["inspect-run", str(workspace), "--run-id", "run_cli"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["status"] == run_summary["status"]
    assert inspected["run_id"] == run_summary["run_id"]
    assert inspected["attempts"] == run_summary["attempts"]
