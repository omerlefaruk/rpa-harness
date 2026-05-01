#!/usr/bin/env python3
"""Propose a patch for a failed workflow based on failure analysis."""
import argparse, json, sys
from pathlib import Path


def propose(report_path: str, workflow_path: str) -> dict:
    from tools.analyze_failure import analyze
    diagnosis = analyze(report_path)

    report = json.loads(Path(report_path).read_text())
    workflow = {}
    if Path(workflow_path).exists():
        import yaml
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

    failed_step_id = report.get("failed_step_id", "")
    failed_step = None
    for step in workflow.get("steps", []):
        if step.get("id") == failed_step_id:
            failed_step = step
            break

    patch = {
        "patch_id": f"patch_{Path(report_path).stem}",
        "risk_level": diagnosis["risk_level"],
        "patch_type": diagnosis["patch_type"],
        "safe_to_apply": diagnosis["safe_to_auto_patch"],
        "target_files": [workflow_path] if Path(workflow_path).exists() else [],
        "reason": diagnosis["root_cause"],
        "evidence": [
            f"Failure report: {report_path}",
            f"Error: {report.get('error_message', '')}",
        ],
        "proposed_diff_summary": "",
        "tests_to_run": diagnosis["required_tests"],
        "requires_human_review": not diagnosis["safe_to_auto_patch"],
    }

    if diagnosis["patch_type"] == "workflow_selector_update":
        patch["proposed_diff_summary"] = (
            f"Update selector for step '{failed_step_id}'. "
            f"Run tools/inspect_page.py on target URL to find stable selectors."
        )
    elif diagnosis["patch_type"] == "timeout_update":
        patch["proposed_diff_summary"] = (
            f"Increase timeout or add wait_for step before '{failed_step_id}'."
        )
    elif diagnosis["patch_type"] == "verification_update":
        patch["proposed_diff_summary"] = (
            f"Review success_check for step '{failed_step_id}'. "
            f"Check if verification is too strict or page state changed."
        )
    elif diagnosis["root_cause"] == "credential_issue":
        patch["proposed_diff_summary"] = (
            "Credential issue detected. Verify environment variables are set. "
            "Do NOT hardcode credentials."
        )

    return patch


def main():
    parser = argparse.ArgumentParser(description="Propose a patch for a failed workflow")
    parser.add_argument("report_path", help="Path to failure_report.json")
    parser.add_argument("--workflow", "-w", required=True, help="Path to workflow YAML")
    args = parser.parse_args()

    patch = propose(args.report_path, args.workflow)
    print(json.dumps({"status": "ok", "patch": patch}, indent=2))


if __name__ == "__main__":
    main()
