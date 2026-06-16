#!/usr/bin/env python3
"""Validate a workflow YAML file against the workflow spec."""
import argparse, sys, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate a workflow YAML")
    parser.add_argument("workflow_path", help="Path to workflow YAML file")
    args = parser.parse_args()

    wf_path = Path(args.workflow_path)
    if not wf_path.exists():
        print(json.dumps({"status": "error", "reason": f"File not found: {args.workflow_path}"}))
        sys.exit(1)

    from harness.rpa.yaml_runner import load_workflow_yaml
    from harness.verification import validate_workflow_report

    try:
        workflow = load_workflow_yaml(wf_path)
    except Exception as e:
        print(json.dumps({"status": "error", "reason": f"YAML parse error: {e}"}))
        sys.exit(1)

    validation = validate_workflow_report(workflow)
    errors = validation["errors"]
    validation["step_count"] = validation["total_steps"]
    validation["checks_count"] = validation["steps_with_success_checks"]

    if errors:
        print(json.dumps({
            "status": "invalid",
            "workflow_id": workflow.get("id", "unknown"),
            **validation,
            "errors": errors,
        }, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "valid",
            "workflow_id": workflow.get("id", "unknown"),
            "type": workflow.get("type", "unknown"),
            **validation,
        }, indent=2))


if __name__ == "__main__":
    main()
