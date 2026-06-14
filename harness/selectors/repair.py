"""Selector repair suggestion helpers."""

from __future__ import annotations

from typing import Any


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
