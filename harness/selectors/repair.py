"""Selector repair suggestion helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from harness.core.artifacts import read_json
from harness.security import redact_value


def selector_repair_plan(
    *,
    workflow_path: str,
    step: dict[str, Any],
    current_url: str | None = None,
) -> dict[str, Any]:
    action = step.get("action", {}) if isinstance(step, dict) else {}
    selector = action.get("selector") if isinstance(action, dict) else None
    intent = step.get("intent") or step.get("description") or step.get("id")
    return {
        "step_id": step.get("id"),
        "intent": intent,
        "failed_selector": selector,
        "selector_evidence": {
            "target_intent": intent,
            "failed_selector": selector,
            "strategy": selector.get("strategy") if isinstance(selector, dict) else None,
            "target_type": "browser",
            "candidates": [],
            "context_artifact": None,
            "validated": False,
        },
        "repair_suggestions": [
            {
                "suggestion": "Prefer data-testid, role/name, label, placeholder, or text before CSS/XPath.",
                "confidence": 0.4,
                "reason": "No deterministic candidate has been validated yet.",
                "evidence_source": current_url,
                "validated": False,
            }
        ],
        "current_url": current_url,
        "recommended_command": _recommended_command(current_url, intent),
        "patch_guidance": (
            "Run selector swarm, choose a stable data-testid/role/label selector, "
            "patch only this step selector, then rerun the workflow success checks."
        ),
        "workflow_path": workflow_path,
    }


def _recommended_command(current_url: str | None, intent: str | None) -> str:
    url = current_url or "https://target-url.example"
    command = f"python main.py --browser-selector-swarm {url}"
    if intent:
        command += f" --browser-selector-swarm-intent \"{intent}\""
    return command


def production_selector_repair(run_dir: str | Path, *, approve: bool = False) -> dict[str, Any]:
    run_path = Path(run_dir)
    if not run_path.exists():
        run_path = Path("runs") / str(run_dir)
    if not run_path.exists():
        return {"status": "blocked", "reason": f"Run not found: {run_dir}"}

    packet = read_json(run_path / "repair_packet.json")
    evidence = read_json(run_path / "evidence_bundle.json")
    selector_evidence = _read_selector_evidence(run_path, evidence)
    candidate = _validated_candidate(selector_evidence)
    workflow_path = (
        packet.get("workflow_path")
        or packet.get("workflow")
        or read_json(run_path / "run_manifest.json").get("workflow_path")
    )
    step_id = packet.get("step_id") or evidence.get("step_id")

    decision = {
        "schema_version": 1,
        "run_dir": str(run_path),
        "status": "blocked",
        "step_id": step_id,
        "workflow_path": workflow_path,
        "candidate": candidate,
        "approved": approve,
    }
    if not candidate:
        decision["reason"] = "No validated selector candidate found."
        return _write_decision(run_path, decision)
    if not approve:
        decision["status"] = "ready"
        decision["reason"] = "Validated candidate found; rerun with --repair-approve to patch workflow."
        return _write_decision(run_path, decision)
    if not workflow_path or not step_id:
        decision["reason"] = "Missing workflow path or step id."
        return _write_decision(run_path, decision)
    patched = _patch_workflow_selector(Path(str(workflow_path)), str(step_id), candidate)
    decision.update(patched)
    return _write_decision(run_path, decision)


def _read_selector_evidence(run_path: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    artifact = (evidence.get("artifacts") or {}).get("selector_evidence")
    if artifact:
        return read_json(run_path / artifact)
    for candidate in (
        run_path / "selector_evidence.json",
        run_path / "artifacts" / "selector_repair_suggestion.json",
    ):
        data = read_json(candidate)
        if data:
            return data.get("selector_evidence") or data
    return {}


def _validated_candidate(selector_evidence: dict[str, Any]) -> dict[str, Any] | None:
    for candidate in selector_evidence.get("candidates", []) or []:
        if candidate.get("validated") is True:
            return candidate
    return None


def _patch_workflow_selector(workflow_path: Path, step_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    if not workflow_path.exists():
        return {"status": "blocked", "reason": f"Workflow not found: {workflow_path}"}
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8")) or {}
    for step in workflow.get("steps", []) or []:
        if step.get("id") != step_id:
            continue
        action = step.setdefault("action", {})
        selector = candidate.get("selector")
        if not isinstance(selector, dict):
            return {"status": "blocked", "reason": "Validated candidate selector is not structured."}
        action["selector"] = selector
        workflow_path.write_text(yaml.safe_dump(redact_value(workflow), sort_keys=False), encoding="utf-8")
        return {
            "status": "applied",
            "reason": "Validated selector candidate applied with approval.",
            "patched_workflow": str(workflow_path),
        }
    return {"status": "blocked", "reason": f"Step not found in workflow: {step_id}"}


def _write_decision(run_path: Path, decision: dict[str, Any]) -> dict[str, Any]:
    safe = redact_value(decision)
    (run_path / "selector_repair_decision.json").write_text(
        json.dumps(safe, indent=2, default=str),
        encoding="utf-8",
    )
    return safe
