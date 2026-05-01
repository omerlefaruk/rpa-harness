"""End-to-end repair loop tests — failure → analyze → propose → fix."""
import json
import tempfile
from pathlib import Path

from harness.reporting.failure_report import FailureReport
from harness.verification import validate_workflow


def test_failure_report_generation():
    """Generate a failure report for a simulated step failure."""
    report = FailureReport(runs_dir=tempfile.mkdtemp())
    report.start_run("test_repair")

    report.log_entry("INFO", "step_1", "Navigating to login page")
    report.log_entry("ERROR", "step_2", "Click failed: Selector not found")

    path = report.generate(
        workflow_id="test_repair",
        workflow_name="Test Repair Workflow",
        failed_step_id="step_2",
        failed_step_description="Click sign in button",
        action_type="browser.click",
        error_type="SelectorNotFoundError",
        error_message="Element 'button:has-text(\"Sign in\")' not found",
        error_category="transient",
        last_successful_step="step_1",
        verification_failures=[
            {"check_type": "selector_visible", "expected": "button visible", "actual": "not found", "message": "Selector not found on page"},
        ],
        evidence={
            "screenshot": "screenshots/failure.png",
            "dom_snapshot": "dom/snapshot.html",
            "current_url": "https://example.com/login",
        },
        duration_ms=2500,
        repro_command="python main.py --run-yaml workflows/examples/browser_login_example.yaml --from-step step_2",
    )

    assert Path(path).exists()
    report_data = json.loads(Path(path).read_text())
    assert report_data["status"] == "failed"
    assert report_data["failed_step_id"] == "step_2"
    assert report_data["error_type"] == "SelectorNotFoundError"
    assert len(report_data["verification_failures"]) == 1


def test_failure_report_evidence():
    """Failure report captures structured evidence."""
    report = FailureReport(runs_dir=tempfile.mkdtemp())
    report.start_run("test_evidence")

    report.save_dom("<html><body><h1>Login</h1></body></html>")
    dom_files = list(Path(report._run_dir).glob("dom/*.html"))
    assert len(dom_files) == 1

    report.save_artifact("console.txt", "[log] page loaded\n[error] JS error")
    artifact_files = list(Path(report._run_dir).glob("artifacts/*.txt"))
    assert len(artifact_files) == 1

    path = report.generate(
        workflow_id="test_evidence",
        workflow_name="Evidence Test",
        failed_step_id="s1",
        failed_step_description="test",
        action_type="browser.click",
        error_type="TimeOutError",
        error_message="Timed out",
    )
    assert Path(path).exists()


def test_failure_analysis_classification():
    """analyze_failure correctly classifies error types."""
    from tools.analyze_failure import classify_error

    assert classify_error("SelectorNotFoundError", "Element #btn not found") == "selector_changed"
    assert classify_error("TimeOutError", "Operation timed out after 30s") == "timing_issue"
    assert classify_error("AuthError", "Authentication failed: invalid credentials") == "credential_issue"
    assert classify_error("ValidationError", "Verification check failed: expected dashboard") == "verification_failed"
    assert classify_error("ConnectionError", "Connection refused to host") == "app_unavailable"
    assert classify_error("ConfigError", "Required env var missing") == "config_issue"
    assert classify_error("UnknownError", "Something completely unexpected") == "unknown"


def test_repair_loop_end_to_end():
    """Full repair loop: failure → analyze → propose → validate fix."""
    import yaml

    # 1. Simulate a workflow with a broken selector
    workflow = {
        "id": "repair_test",
        "name": "Repair Test",
        "version": "1.0",
        "type": "browser",
        "steps": [{
            "id": "goto_login",
            "action": {"type": "browser.goto", "url": "https://example.com/login"},
            "success_check": [{"type": "url_contains", "value": "/login"}],
        }, {
            "id": "click_old_button",
            "action": {
                "type": "browser.click",
                "selector": {"strategy": "css", "value": "#old-btn-id"},
            },
            "success_check": [{"type": "selector_visible", "value": "dashboard"}],
        }],
    }

    # 2. Validate the workflow — should pass (has success checks)
    errors = validate_workflow(workflow)
    assert len(errors) == 0

    # 3. Generate a simulated failure report
    report = FailureReport(runs_dir=tempfile.mkdtemp())
    report.start_run("repair_test")
    report_path = report.generate(
        workflow_id="repair_test",
        workflow_name="Repair Test",
        failed_step_id="click_old_button",
        failed_step_description="Click old button",
        action_type="browser.click",
        error_type="SelectorNotFoundError",
        error_message="Element '#old-btn-id' not found on page",
        error_category="transient",
        last_successful_step="goto_login",
        evidence={"current_url": "https://example.com/login"},
        repro_command="python main.py --run-yaml repair_test.yaml",
    )

    # 4. Analyze failure
    from tools.analyze_failure import analyze
    diagnosis = analyze(report_path)
    assert diagnosis["root_cause"] == "selector_changed"
    assert diagnosis["safe_to_auto_patch"] is True
    assert diagnosis["risk_level"] == "low"

    # 5. After analyzing, a human/agent would update the selector
    # Simulate the fix: change #old-btn-id to a better selector
    workflow["steps"][1]["action"]["selector"] = {"strategy": "data-testid", "value": "sign-in-btn"}
    workflow["steps"][1]["success_check"] = [
        {"type": "visible_text", "value": "Dashboard"},
    ]

    # 6. Verify the fix passes validation
    errors = validate_workflow(workflow)
    assert len(errors) == 0

    # 7. The patched workflow has a better selector
    assert workflow["steps"][1]["action"]["selector"]["strategy"] == "data-testid"


def test_patch_proposal_respects_risk():
    """propose_patch flags high-risk changes."""
    import json, tempfile, yaml
    from pathlib import Path

    # Create a temp report suggesting credential issue
    report = FailureReport(runs_dir=tempfile.mkdtemp())
    report.start_run("cred_test")
    report_path = report.generate(
        workflow_id="cred_test", workflow_name="Cred Test",
        failed_step_id="login", failed_step_description="Login",
        action_type="browser.fill",
        error_type="AuthenticationError",
        error_message="Invalid credentials: unauthorized",
        error_category="permanent",
    )

    # Create temp workflow
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({"id": "cred_test", "name": "Cred Test", "version": "1.0", "type": "browser", "steps": []}, f)
        wf_path = f.name

    from tools.propose_patch import propose
    patch = propose(report_path, wf_path)

    assert patch["requires_human_review"] is True
    assert patch["risk_level"] == "high"

    Path(wf_path).unlink(missing_ok=True)


def test_verify_weakening_is_rejected():
    """Removing success checks should fail validation."""
    workflow = {
        "id": "weak_test",
        "name": "Weak Test",
        "version": "1.0",
        "type": "browser",
        "steps": [{
            "id": "s1",
            "action": {"type": "browser.click"},
            # Missing success_check — should fail
        }],
    }
    errors = validate_workflow(workflow)
    assert any("missing success_check" in error for error in errors)
