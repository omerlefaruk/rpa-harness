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

    from harness.verification import validate_workflow

    try:
        import yaml
    except ImportError:
        print(json.dumps({"status": "error", "reason": "pyyaml not installed"}))
        sys.exit(1)

    try:
        workflow = yaml.safe_load(wf_path.read_text())
    except Exception as e:
        print(json.dumps({"status": "error", "reason": f"YAML parse error: {e}"}))
        sys.exit(1)

    errors = validate_workflow(workflow)
    step_count = len(workflow.get("steps", []))
    checks_count = sum(
        len(step.get("success_check", [])) for step in workflow.get("steps", [])
    )

    if errors:
        print(json.dumps({
            "status": "invalid",
            "workflow_id": workflow.get("id", "unknown"),
            "step_count": step_count,
            "checks_count": checks_count,
            "errors": errors,
        }, indent=2))
        sys.exit(1)
    else:
        print(json.dumps({
            "status": "valid",
            "workflow_id": workflow.get("id", "unknown"),
            "type": workflow.get("type", "unknown"),
            "step_count": step_count,
            "checks_count": checks_count,
        }, indent=2))


if __name__ == "__main__":
    main()
