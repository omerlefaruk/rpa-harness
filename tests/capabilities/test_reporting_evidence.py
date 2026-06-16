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
    assert report["error_class"] == "unknown"
    assert (Path(report_path).parent / "artifacts" / "api_response.json").exists()


def test_failure_report_writes_redacted_evidence_bundle(tmp_path):
    failure = FailureReport(str(tmp_path / "runs"))
    failure.start_run("bundle_failure")
    failure.log_entry(
        "ERROR",
        "read_api",
        "Authorization: Bearer rpa-canary-token",
        extra={"password": "fake-password-do-not-log"},
    )

    report_path = failure.generate(
        workflow_id="bundle_failure",
        workflow_name="Bundle Failure",
        failed_step_id="read_api",
        failed_step_description="Read API",
        action_type="api.get",
        error_type="WorkflowStepFailed",
        error_message="status_code failed",
        verification_failures=[
            {
                "check_type": "status_code",
                "expected": 200,
                "actual": 500,
                "message": "Authorization: Bearer rpa-canary-token",
                "secret": "RPA_SECRET_CANARY_12345",
                "password": "fake-password-do-not-log",
                "api_key": "sk-test-canary-12345",
            }
        ],
        evidence={"api_response": "artifacts/api_response.json"},
    )

    report = json.loads(Path(report_path).read_text())
    bundle_path = Path(report_path).parent / "evidence_bundle.json"
    bundle_text = bundle_path.read_text()
    bundle = json.loads(bundle_text)
    repair_packet_path = Path(report_path).parent / "repair_packet.json"
    repair_packet_text = repair_packet_path.read_text()
    repair_packet = json.loads(repair_packet_text)
    logs_text = (Path(report_path).parent / "logs.jsonl").read_text()

    assert report["schema_version"] == "1"
    assert report["failure_kind"] == "verification_failed"
    assert report["evidence"]["evidence_bundle"] == "evidence_bundle.json"
    assert report["evidence"]["repair_packet"] == "repair_packet.json"
    assert bundle["schema_version"] == "1"
    assert bundle["failure_kind"] == "verification_failed"
    assert bundle["target_type"] == "api"
    assert bundle["artifacts"]["api_preview"] == "artifacts/api_response.json"
    assert bundle["artifacts"]["repair_packet"] == "repair_packet.json"
    assert repair_packet["schema_version"] == "1"
    assert repair_packet["failure_kind"] == "verification_failed"
    assert repair_packet["recommended_next_action"]
    for canary in [
        "RPA_SECRET_CANARY_12345",
        "fake-password-do-not-log",
        "sk-test-canary-12345",
        "Bearer rpa-canary-token",
    ]:
        assert canary not in bundle_text
        assert canary not in repair_packet_text
        assert canary not in logs_text


def test_failure_report_includes_rulebook_failure_fields(tmp_path):
    failure = FailureReport(str(tmp_path / "runs"))
    failure.start_run("rulebook_failure")

    report_path = failure.generate(
        workflow_id="rulebook_failure",
        workflow_name="Rulebook Failure",
        failed_step_id="submit_invoice",
        failed_step_description="Submit invoice",
        action_type="browser.click",
        error_type="AuthenticationError",
        error_message="Login denied",
        error_category="permanent",
        current_stage="submit invoice",
        intended_action="Create invoice in target system",
        expected_result="Invoice confirmation is visible",
        actual_result="Login denied banner is visible",
        input_record_id="row-42",
        target_system="billing_portal",
        retry_attempt=1,
        max_attempts=1,
        retry_allowed=False,
        side_effect_risk="medium",
        human_review_required=True,
        first_failed_stage="submit invoice",
        last_known_good_stage="open invoice form",
        escalation_status="needs_operator_review",
        error_class="authorization_config",
    )

    report = json.loads(Path(report_path).read_text())

    assert report["current_stage"] == "submit invoice"
    assert report["intended_action"] == "Create invoice in target system"
    assert report["expected_result"] == "Invoice confirmation is visible"
    assert report["actual_result"] == "Login denied banner is visible"
    assert report["input_record_id"] == "row-42"
    assert report["target_system"] == "billing_portal"
    assert report["retry_attempt"] == 1
    assert report["max_attempts"] == 1
    assert report["retry_allowed"] is False
    assert report["side_effect_risk"] == "medium"
    assert report["human_review_required"] is True
    assert report["first_failed_stage"] == "submit invoice"
    assert report["last_known_good_stage"] == "open invoice form"
    assert report["escalation_status"] == "needs_operator_review"
    assert report["error_class"] == "authorization_config"
    assert report["error_category"] == "permanent"


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
