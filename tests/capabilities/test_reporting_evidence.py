"""Capability characterization for reports and failure evidence."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from harness.config import HarnessConfig
from harness.orchestrator import AutomationHarness
from harness.reporting import JSONReporter
from harness.reporting.failure_report import FailureReport
from harness.rpa.workflow import WorkflowResult, WorkflowStatus
from harness.test_case import TestResult as HarnessTestResult
from harness.test_case import TestStatus as HarnessTestStatus


def _config(tmp_path: Path) -> HarnessConfig:
    return HarnessConfig(
        headless=True,
        enable_vision=False,
        report_dir=str(tmp_path / "reports"),
        screenshot_dir=str(tmp_path / "screenshots"),
    )


def test_json_report_includes_test_and_workflow_metadata(tmp_path):
    harness = AutomationHarness(_config(tmp_path))
    harness._start_time = 1.0
    harness._end_time = 2.0
    harness.results = [
        HarnessTestResult(
            name="metadata_test",
            status=HarnessTestStatus.PASSED,
            start_time=datetime.now(),
            end_time=datetime.now(),
            metadata={"type": "automation_test", "tags": ["capability"]},
        )
    ]
    harness.workflow_results = [
        WorkflowResult(
            name="metadata_workflow",
            status=WorkflowStatus.PASSED,
            total_records=2,
            processed_records=1,
            failed_records=1,
            output_files=[str(tmp_path / "mismatches.xlsx")],
        )
    ]

    paths = harness.report(formats=["json"])
    report = json.loads(Path(paths["json"]).read_text())
    workflow_entry = next(test for test in report["tests"] if test["name"] == "metadata_workflow")

    assert report["metadata"]["harness_version"] == "0.1.0"
    assert report["metadata"]["config"]["enable_vision"] is False
    assert workflow_entry["metadata"]["type"] == "rpa_workflow"
    assert workflow_entry["metadata"]["total_records"] == 2
    assert workflow_entry["metadata"]["failed_records"] == 1
    assert workflow_entry["metadata"]["output_files"] == [str(tmp_path / "mismatches.xlsx")]


def test_failure_report_includes_repro_command_and_evidence_paths(tmp_path):
    failure = FailureReport(str(tmp_path / "runs"))
    failure.start_run("capability_failure")
    artifact_path = failure.save_artifact("api_response.json", '{"status_code": 500}')

    report_path = failure.generate(
        workflow_id="capability_failure",
        workflow_name="Capability Failure",
        failed_step_id="read_api",
        failed_step_description="Read API",
        action_type="api.get",
        error_type="WorkflowStepFailed",
        error_message="status_code failed",
        verification_failures=[{"check_type": "status_code", "expected": 200, "actual": "500"}],
        evidence={"api_response": str(Path(artifact_path).name)},
        repro_command="python main.py --run-yaml workflows/capabilities/local_api_read.yaml",
    )

    report = json.loads(Path(report_path).read_text())

    assert report["repro_command"] == (
        "python main.py --run-yaml workflows/capabilities/local_api_read.yaml"
    )
    assert report["evidence"]["api_response"] == "api_response.json"
    assert report["evidence"]["artifact_paths"] == ["api_response.json"]
    assert report["last_successful_step"] is None
    assert (Path(report_path).parent / "artifacts" / "api_response.json").exists()


def test_json_report_redacts_secret_like_log_values(tmp_path):
    report_path = JSONReporter(str(tmp_path / "reports")).generate(
        [
            HarnessTestResult(
                name="secret_log",
                status=HarnessTestStatus.PASSED,
                logs=["Authorization: Bearer fixture-secret-value"],
            )
        ],
        suite_name="secret-redaction",
    )

    assert "fixture-secret-value" not in Path(report_path).read_text()
