"""Tests for agent-facing autopilot execution."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.config import HarnessConfig


def _workflow(path: Path) -> None:
    path.write_text(
        """
id: autopilot_noop
name: Autopilot Noop
version: "1.0"
type: api
steps:
  - id: done
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_run_autopilot_build_validates_preflights_and_runs(tmp_path, monkeypatch):
    from harness.autopilot import run_autopilot_build

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    _workflow(wf_path)
    task_path.write_text(f"Build and run this automation.\nworkflow: {wf_path}\n", encoding="utf-8")

    result = await run_autopilot_build(str(task_path), config=HarnessConfig())

    assert result["status"] == "passed"
    assert result["workflow_path"] == str(wf_path)
    assert [step["name"] for step in result["steps"]] == ["validate", "preflight", "run"]
    assert result["steps"][-1]["result"]["status"] == "passed"
    assert Path(result["run_dir"], "report.html").exists()


@pytest.mark.asyncio
async def test_run_autopilot_build_exposes_execution_plan_for_record_loop(tmp_path, monkeypatch):
    from harness.autopilot import run_autopilot_build

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "loop.yaml"
    task_path = tmp_path / "task.md"
    wf_path.write_text(
        """
id: autopilot_loop
name: Autopilot Loop
version: "1.0"
type: api
inputs:
  rows:
    - invoice_id: A-1
    - invoice_id: B-2
steps:
  - id: process_row
    phase: process_records
    for_each:
      input: rows
      record_id: invoice_id
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )
    task_path.write_text(f"Build and run this automation.\nworkflow: {wf_path}\n", encoding="utf-8")

    result = await run_autopilot_build(str(task_path), config=HarnessConfig())

    assert result["status"] == "passed"
    assert result["execution_plan"]["total_units"] == 2
    assert result["execution_plan"]["record_units"] == 2
    assert [step["record_id"] for step in result["steps"][-1]["result"]["steps"]] == ["A-1", "B-2"]


@pytest.mark.asyncio
async def test_run_autopilot_build_blocks_external_writes_by_policy(tmp_path, monkeypatch):
    from harness.autopilot import run_autopilot_build

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "write.yaml"
    task_path = tmp_path / "task.md"
    wf_path.write_text(
        """
id: autopilot_write
name: Autopilot Write
version: "1.0"
type: api
allow_destructive: true
steps:
  - id: write
    side_effect: external_write
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )
    task_path.write_text(f"Run it.\nworkflow: {wf_path}\n", encoding="utf-8")

    result = await run_autopilot_build(str(task_path), config=HarnessConfig())

    assert result["status"] == "blocked"
    assert result["steps"][-1]["name"] == "policy"
    assert "external writes are disabled" in result["steps"][-1]["result"]["violations"][0]["reason"]


@pytest.mark.asyncio
async def test_run_autopilot_build_blocks_approval_gated_steps_by_policy(tmp_path, monkeypatch):
    from harness.autopilot import run_autopilot_build

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "approval.yaml"
    task_path = tmp_path / "task.md"
    wf_path.write_text(
        """
id: approval_required
name: Approval Required
version: "1.0"
type: api
steps:
  - id: submit
    requires_approval: true
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )
    task_path.write_text(f"Run it.\nworkflow: {wf_path}\n", encoding="utf-8")

    result = await run_autopilot_build(str(task_path), config=HarnessConfig())

    assert result["status"] == "blocked"
    assert result["steps"][-1]["name"] == "policy"
    assert "approval-gated actions are disabled" in result["steps"][-1]["result"]["violations"][0]["reason"]


@pytest.mark.asyncio
async def test_run_autopilot_build_applies_policy_browser_cdp_endpoint(tmp_path, monkeypatch):
    from harness import autopilot as autopilot_module

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    policy_path = tmp_path / "policy.yaml"
    _workflow(wf_path)
    task_path.write_text(f"Run it.\nworkflow: {wf_path}\n", encoding="utf-8")
    policy_path.write_text(
        """
autopilot:
  browser_cdp_endpoint: http://127.0.0.1:9222
""",
        encoding="utf-8",
    )
    seen = {}

    class FakeRunner:
        def __init__(self, config):
            seen["endpoint"] = config.browser_cdp_endpoint

        async def preflight(self, workflow):
            return {"status": "passed"}

        async def run(self, workflow):
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            return {"status": "passed", "run_id": "run-1", "run_dir": str(run_dir)}

    monkeypatch.setattr(autopilot_module, "YamlWorkflowRunner", FakeRunner)

    result = await autopilot_module.run_autopilot_build(
        str(task_path),
        config=HarnessConfig(),
        policy_path=policy_path,
    )

    assert result["status"] == "passed"
    assert seen["endpoint"] == "http://127.0.0.1:9222"


def test_autopilot_cli_outputs_json(tmp_path):
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    _workflow(wf_path)
    task_path.write_text("Build and run this automation.\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--autopilot-build",
            str(task_path),
            "--autopilot-workflow",
            str(wf_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "passed"
    assert payload["workflow_path"] == str(wf_path)
    assert payload["steps"][-1]["name"] == "run"


def test_autopilot_policy_and_command_manifest_are_agent_readable():
    import yaml

    policy = yaml.safe_load(Path(".agents/config/autopilot.yaml").read_text(encoding="utf-8"))
    manifest = json.loads(Path(".agents/config/agent_command_manifest.json").read_text(encoding="utf-8"))
    skill = Path(".agents/skills/rpa-harness-automation-builder/SKILL.md").read_text(encoding="utf-8")

    assert policy["autopilot"]["require_success_checks"] is True
    assert policy["autopilot"]["allow_coordinate_fallback"] is False
    assert "autopilot_build" in manifest["commands"]
    assert manifest["commands"]["autopilot_build"]["output"] == "json"
    assert "--autopilot-build" in skill
