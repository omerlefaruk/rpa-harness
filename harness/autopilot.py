"""Agent-facing autopilot orchestration over the existing CLI/runtime."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from harness.builder import create_builder_session
from harness.config import HarnessConfig
from harness.rpa.execution_plan import ExecutionPlan, build_execution_plan
from harness.rpa.yaml_runner import YamlWorkflowRunner, load_workflow_yaml
from harness.security import redact_value
from harness.verification import validate_workflow_report

DEFAULT_POLICY_PATH = Path(".agents/config/autopilot.yaml")
DEFAULT_COMMAND_MANIFEST_PATH = Path(".agents/config/agent_command_manifest.json")
WORKFLOW_LINE_RE = re.compile(r"^\s*workflow(?:_path)?:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
EXTERNAL_WRITE_ACTIONS = {"api.post", "api.put", "api.patch", "api.delete"}


def load_autopilot_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    policy_path = Path(path)
    if not policy_path.exists():
        return {"autopilot": _default_policy()}
    loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    autopilot = dict(_default_policy())
    autopilot.update(loaded.get("autopilot") or {})
    return {"autopilot": autopilot}


def load_command_manifest(path: str | Path = DEFAULT_COMMAND_MANIFEST_PATH) -> dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {"schema_version": 1, "commands": {}}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


async def run_autopilot_build(
    task_path: str | Path,
    *,
    workflow_path: str | Path | None = None,
    config: HarnessConfig | None = None,
    policy_path: str | Path = DEFAULT_POLICY_PATH,
    manifest_path: str | Path = DEFAULT_COMMAND_MANIFEST_PATH,
) -> dict[str, Any]:
    task = Path(task_path)
    policy = load_autopilot_policy(policy_path)
    manifest = load_command_manifest(manifest_path)
    builder_session = create_builder_session(task)
    workflow = _resolve_workflow_path(task, workflow_path)
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "task_path": str(task),
        "workflow_path": str(workflow) if workflow else None,
        "builder_session": str(builder_session),
        "policy": redact_value(policy),
        "command_manifest": str(Path(manifest_path)),
        "available_commands": sorted((manifest.get("commands") or {}).keys()),
        "steps": [],
    }
    if not workflow:
        result.update(
            {
                "status": "blocked",
                "reason": "No workflow path provided. Add 'workflow: path/to/workflow.yaml' to the task or pass --autopilot-workflow.",
            }
        )
        return result

    try:
        loaded_workflow = load_workflow_yaml(workflow)
    except Exception as exc:
        result["steps"].append(_step("load_workflow", "failed", {"error": str(exc)}))
        result.update({"status": "failed", "reason": str(exc)})
        return result

    validation = validate_workflow_report(loaded_workflow)
    result["steps"].append(_step("validate", "passed" if not validation["errors"] else "failed", validation))
    if validation["errors"]:
        result.update({"status": "failed", "reason": "Workflow validation failed"})
        return result

    execution_plan = build_execution_plan(
        loaded_workflow,
        inputs=loaded_workflow.get("inputs", {}) or {},
    )
    result["execution_plan"] = execution_plan.summary()

    violations = _policy_violations(loaded_workflow, policy, execution_plan)
    if violations:
        result["steps"].append(_step("policy", "blocked", {"violations": violations}))
        result.update({"status": "blocked", "reason": "Autopilot policy blocked this workflow"})
        return result

    runner_config = config or HarnessConfig.from_env()
    policy_endpoint = (policy.get("autopilot") or {}).get("browser_cdp_endpoint")
    if policy_endpoint and not runner_config.browser_cdp_endpoint:
        runner_config.browser_cdp_endpoint = policy_endpoint
    preflight = await YamlWorkflowRunner(runner_config).preflight(str(workflow))
    result["steps"].append(_step("preflight", preflight.get("status", "unknown"), preflight))
    if preflight.get("status") != "passed":
        result.update({"status": "failed", "reason": "Preflight failed"})
        return result

    run = await YamlWorkflowRunner(runner_config).run(str(workflow))
    result["steps"].append(_step("run", run.get("status", "unknown"), run))
    result.update(
        {
            "status": run.get("status", "unknown"),
            "run_id": run.get("run_id"),
            "run_dir": run.get("run_dir"),
            "report": str(Path(run["run_dir"]) / "report.html") if run.get("run_dir") else None,
        }
    )
    if run.get("status") != "passed":
        result["reason"] = run.get("reason", "Workflow run failed")
    return redact_value(result)


def _resolve_workflow_path(task: Path, workflow_path: str | Path | None) -> Path | None:
    if workflow_path:
        return Path(workflow_path)
    text = task.read_text(encoding="utf-8", errors="replace")
    match = WORKFLOW_LINE_RE.search(text)
    if not match:
        return None
    path = Path(match.group(1).strip().strip('"'))
    return path if path.is_absolute() else (task.parent / path)


def _policy_violations(
    workflow: dict[str, Any],
    policy: dict[str, Any],
    execution_plan: ExecutionPlan | None = None,
) -> list[dict[str, Any]]:
    autopilot = policy.get("autopilot") or {}
    violations = []
    plan = execution_plan or build_execution_plan(
        workflow,
        inputs=workflow.get("inputs", {}) or {},
    )
    for step in plan.steps:
        action = step.get("action") or {}
        action_type = str(action.get("type") or "no_op")
        side_effect = str(step.get("side_effect") or "").lower()
        if not autopilot.get("allow_submit") and _requires_operator_submit(step, action):
            violations.append(
                {
                    "step": step.get("id"),
                    "reason": "submit or approval-gated actions are disabled by autopilot policy",
                    "action_type": action_type,
                }
            )
        if not autopilot.get("allow_external_writes") and (
            side_effect in {"external_write", "destructive"} or action_type in EXTERNAL_WRITE_ACTIONS
        ):
            violations.append(
                {
                    "step": step.get("id"),
                    "reason": "external writes are disabled by autopilot policy",
                    "action_type": action_type,
                    "side_effect": side_effect,
                }
            )
        selector = action.get("selector") or {}
        strategy = str(selector.get("strategy") or "").lower()
        if not autopilot.get("allow_coordinate_fallback") and strategy in {"coordinate", "coordinates"}:
            violations.append(
                {
                    "step": step.get("id"),
                    "reason": "coordinate fallback is disabled by autopilot policy",
                    "action_type": action_type,
                    "selector_strategy": strategy,
                }
            )
    return violations


def _requires_operator_submit(step: dict[str, Any], action: dict[str, Any]) -> bool:
    return any(
        bool(value)
        for value in (
            step.get("requires_approval"),
            step.get("approval_required"),
            action.get("requires_approval"),
            action.get("approval_required"),
        )
    )


def _step(name: str, status: str, step_result: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": status, "result": redact_value(step_result)}


def _default_policy() -> dict[str, Any]:
    return {
        "allow_external_writes": False,
        "allow_submit": False,
        "allow_coordinate_fallback": False,
        "require_success_checks": True,
        "run_real_workflows": True,
        "browser_cdp_endpoint": None,
    }
