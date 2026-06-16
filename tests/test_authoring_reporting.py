"""Tests for workflow authoring, report rendering, bundles, and ledger helpers."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml

from harness.reporting.dashboard import collect_run_reports
from harness.reporting.evidence_bundle import bundle_run
from harness.reporting.failure_html import render_failure_report_html
from harness.rpa.ledger import ResumeLedger
from harness.rpa.templates import TEMPLATE_NAMES, workflow_template, write_workflow_template
from harness.selectors.repair import selector_repair_plan
from harness.verification import validate_workflow


def test_workflow_templates_are_valid_and_rulebook_ready():
    for template_name in TEMPLATE_NAMES:
        workflow = workflow_template(
            template_name,
            workflow_id=f"{template_name}_test",
            target_system="fixture-system",
        )
        assert validate_workflow(workflow) == []
        assert workflow["schema_version"] == "1"
        assert workflow["owner"] == "ops"
        assert workflow["target_systems"] == ["fixture-system"]


def test_new_workflow_cli_writes_valid_template(tmp_path):
    path = tmp_path / "generated.yaml"

    completed = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--new-workflow",
            str(path),
            "--workflow-template",
            "api_read_write",
            "--workflow-id",
            "generated_api",
            "--target-system",
            "fixture-api",
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "Workflow written" in completed.stdout
    assert workflow["id"] == "generated_api"
    assert validate_workflow(workflow) == []


def test_failure_report_html_and_evidence_bundle(tmp_path):
    run_dir = tmp_path / "runs" / "20260614_fixture"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "api_response.json").write_text('{"status_code": 500}')
    report = {
        "workflow_name": "Fixture Workflow",
        "run_id": "fixture-run",
        "status": "failed",
        "current_stage": "read_resource",
        "failed_step_id": "read",
        "action_type": "api.get",
        "intended_action": "read API resource",
        "expected_result": "200",
        "actual_result": "500",
        "error_class": "external_system",
        "error_message": "API returned 500",
        "verification_failures": [
            {
                "check_type": "status_code",
                "expected": 200,
                "actual": 500,
                "message": "status mismatch",
            }
        ],
        "evidence": {"api_response": "artifacts/api_response.json"},
    }
    report_path = run_dir / "failure_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    html_path = render_failure_report_html(report_path)
    bundle_path = bundle_run(run_dir)

    assert html_path.exists()
    assert "Fixture Workflow failure" in html_path.read_text(encoding="utf-8")
    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path) as bundle:
        assert "failure_report.json" in bundle.namelist()
        assert "bundle_manifest.json" in bundle.namelist()


def test_resume_ledger_records_latest_status(tmp_path):
    ledger = ResumeLedger(tmp_path / "ledger.jsonl")
    ledger.record_item("wf", "1", "pending", stage="load")
    ledger.record_item("wf", "1", "passed", stage="done", external_reference_id="EXT-1")

    summary = ledger.summary("wf")

    assert summary["records"] == 1
    assert summary["status_counts"] == {"passed": 1}
    assert summary["latest"]["1"]["external_reference_id"] == "EXT-1"


def test_selector_repair_plan_contains_swarm_command():
    plan = selector_repair_plan(
        workflow_path="workflow.yaml",
        step={
            "id": "click_save",
            "intent": "Save form",
            "action": {"type": "browser.click", "selector": {"strategy": "text", "value": "Save"}},
        },
        current_url="https://example.test/form",
    )

    assert plan["step_id"] == "click_save"
    assert "--browser-selector-swarm" in plan["recommended_command"]
    assert "Save form" in plan["recommended_command"]
    assert plan["selector_evidence"]["target_intent"] == "Save form"
    assert plan["selector_evidence"]["validated"] is False
    assert plan["repair_suggestions"][0]["confidence"] == 0.4
    assert plan["repair_suggestions"][0]["validated"] is False


def test_dashboard_collects_run_failure_metadata(tmp_path):
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    (run_dir / "evidence_bundle.json").write_text("{}", encoding="utf-8")
    (run_dir / "repair_packet.json").write_text("{}", encoding="utf-8")
    (run_dir / "failure_report.json").write_text(
        json.dumps(
            {
                "run_id": "run_1",
                "workflow_name": "Workflow",
                "status": "failed",
                "failure_kind": "selector_not_found",
                "error_class": "automation_defect",
                "current_stage": "click_save",
                "failed_step_id": "save",
                "human_review_required": True,
            }
        ),
        encoding="utf-8",
    )

    reports = collect_run_reports(tmp_path / "runs")

    assert reports[0]["run_id"] == "run_1"
    assert reports[0]["failure_kind"] == "selector_not_found"
    assert reports[0]["error_class"] == "automation_defect"
    assert reports[0]["evidence_bundle"].endswith("evidence_bundle.json")
    assert reports[0]["repair_packet"].endswith("repair_packet.json")
