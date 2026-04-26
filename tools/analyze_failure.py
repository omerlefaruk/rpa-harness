#!/usr/bin/env python3
"""Analyze a failure report and produce structured diagnosis."""
import argparse, json, sys
from pathlib import Path


def classify_error(error_type: str, error_message: str) -> str:
    msg = (error_type + " " + error_message).lower()
    if any(k in msg for k in ("selector", "not found", "locator", "no element")):
        return "selector_changed"
    if any(k in msg for k in ("timeout", "timed out", "wait")):
        return "timing_issue"
    if any(k in msg for k in ("credential", "auth", "login", "password", "unauthorized", "forbidden")):
        return "credential_issue"
    if any(k in msg for k in ("verification check failed", "expected '", "expected value", "check failed")):
        return "verification_failed"
    if any(k in msg for k in ("connection", "network", "dns", "refused", "unreachable")):
        return "app_unavailable"
    if any(k in msg for k in ("config", "missing", "not set", "environment")):
        return "config_issue"
    return "unknown"


def analyze(report_path: str) -> dict:
    report = json.loads(Path(report_path).read_text())

    error_type = report.get("error_type", "")
    error_message = report.get("error_message", "")
    category = classify_error(error_type, error_message)

    patch_types = {
        "selector_changed": "workflow_selector_update",
        "timing_issue": "timeout_update",
        "verification_failed": "verification_update",
        "credential_issue": "credential_issue",
        "app_unavailable": "unknown",
        "config_issue": "config_issue",
        "unknown": "unknown",
    }

    risk_levels = {
        "selector_changed": "low",
        "timing_issue": "low",
        "verification_failed": "medium",
        "credential_issue": "high",
        "app_unavailable": "high",
        "config_issue": "low",
        "unknown": "medium",
    }

    safe_to_patch = category in ("selector_changed", "timing_issue", "config_issue")

    repro_cmd = report.get("repro_command", "")
    if not repro_cmd:
        workflow_id = report.get("workflow_id", "unknown")
        failed_step = report.get("failed_step_id", "")
        repro_cmd = f"python -m harness.cli run workflows/{workflow_id}.yaml"
        if failed_step:
            repro_cmd += f" --from-step {failed_step}"

    return {
        "root_cause": category,
        "confidence": 0.85 if category != "unknown" else 0.3,
        "patch_type": patch_types[category],
        "safe_to_auto_patch": safe_to_patch,
        "risk_level": risk_levels[category],
        "required_tests": [
            f"pytest tests/ -k {report.get('workflow_id', 'workflow')}",
        ],
        "repro_command": repro_cmd,
        "proposed_changes": [],
        "evidence_summary": {
            "screenshot": bool(report.get("evidence", {}).get("screenshot")),
            "dom_snapshot": bool(report.get("evidence", {}).get("dom_snapshot")),
            "console_logs": bool(report.get("evidence", {}).get("console_logs")),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze a failure report")
    parser.add_argument("report_path", help="Path to failure_report.json")
    args = parser.parse_args()

    if not Path(args.report_path).exists():
        print(json.dumps({"status": "error", "reason": f"File not found: {args.report_path}"}))
        sys.exit(1)

    diagnosis = analyze(args.report_path)
    print(json.dumps({"status": "ok", "diagnosis": diagnosis}, indent=2))


if __name__ == "__main__":
    main()
