"""Workflow templates and authoring helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


TEMPLATE_NAMES = (
    "browser_login_export",
    "excel_row_loop",
    "api_read_write",
    "desktop_form_fill",
    "browser_scrape",
    "reconciliation",
)


def workflow_template(
    template: str,
    workflow_id: str,
    name: str | None = None,
    owner: str = "ops",
    target_system: str = "target-system",
) -> dict[str, Any]:
    if template not in TEMPLATES:
        raise ValueError(f"Unknown workflow template: {template}")
    workflow = deepcopy(TEMPLATES[template])
    workflow["id"] = workflow_id
    workflow["name"] = name or workflow_id.replace("_", " ").title()
    workflow["owner"] = owner
    workflow["target_systems"] = [target_system]
    return workflow


def write_workflow_template(
    path: str | Path,
    template: str,
    workflow_id: str,
    name: str | None = None,
    owner: str = "ops",
    target_system: str = "target-system",
) -> Path:
    workflow = workflow_template(
        template=template,
        workflow_id=workflow_id,
        name=name,
        owner=owner,
        target_system=target_system,
    )
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return destination


def prompt_for_workflow(path: str | Path) -> Path:
    template = _ask("Template", "browser_login_export")
    workflow_id = _ask("Workflow id", "new_rpa_workflow")
    name = _ask("Workflow name", workflow_id.replace("_", " ").title())
    owner = _ask("Owner", "ops")
    target = _ask("Target system", "target-system")
    return write_workflow_template(path, template, workflow_id, name, owner, target)


def _ask(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


BASE_CONTRACT = {
    "version": "1.0",
    "input_schema": {"record_id": "string"},
    "output_destination": "runs/output",
    "system_of_record": "target-system",
    "success_condition": "Verified business state matches the input record.",
    "safe_test_case": "Use a non-production fixture record before production.",
    "allowed_side_effects": [],
    "rerun_policy": "Safe to rerun only after checking record status and external reference id.",
    "escalation_owner": "ops",
}


TEMPLATES: dict[str, dict[str, Any]] = {
    "browser_login_export": {
        **BASE_CONTRACT,
        "type": "browser",
        "description": "Login, export a file, and verify the exported artifact.",
        "inputs": {"base_url": "https://example.com", "download_path": "runs/downloads/export.csv"},
        "credentials": {"username": "APP_USERNAME", "password": "APP_PASSWORD"},
        "allowed_side_effects": ["export_file"],
        "steps": [
            {
                "id": "open_login",
                "current_stage": "open_login_page",
                "intent": "Open the login page for the target system.",
                "preconditions": ["base_url points to the intended environment"],
                "postconditions": ["login page is loaded"],
                "proof": "URL contains /login",
                "failure_path": "stop and capture browser evidence",
                "action": {"type": "browser.goto", "url": "${inputs.base_url}/login"},
                "success_check": [{"type": "url_contains", "value": "/login"}],
            },
            {
                "id": "verify_export",
                "current_stage": "verify_export_file",
                "intent": "Verify the expected export file exists.",
                "preconditions": ["export action has completed"],
                "postconditions": ["export file exists"],
                "proof": "file_exists check",
                "failure_path": "stop and escalate with artifact evidence",
                "action": {"type": "no_op"},
                "success_check": [{"type": "file_exists", "value": "${inputs.download_path}"}],
            },
        ],
    },
    "excel_row_loop": {
        **BASE_CONTRACT,
        "type": "excel",
        "description": "Read rows from Excel and write a processed workbook.",
        "inputs": {"workbook": "data/input.xlsx", "output": "data/output.xlsx"},
        "allowed_side_effects": ["write_workbook"],
        "steps": [
            {
                "id": "read_rows",
                "current_stage": "read_input_rows",
                "intent": "Load input rows from the workbook.",
                "preconditions": ["input workbook exists"],
                "postconditions": ["rows are available"],
                "proof": "row_count output",
                "failure_path": "stop before side effects",
                "action": {"type": "excel.read", "path": "${inputs.workbook}", "output": "rows"},
                "success_check": [{"type": "variable_has_value", "value": "rows"}],
            }
        ],
    },
    "api_read_write": {
        **BASE_CONTRACT,
        "type": "api",
        "description": "Read an API resource, write a safe update, and verify response state.",
        "inputs": {"api_base_url": "https://api.example.com", "record_id": "fixture-1"},
        "credentials": {"api_token": "API_TOKEN"},
        "allowed_side_effects": ["api_update"],
        "steps": [
            {
                "id": "read_resource",
                "current_stage": "read_resource",
                "intent": "Read the target resource before writing.",
                "preconditions": ["API token is configured"],
                "postconditions": ["API returns 200"],
                "proof": "status_code and JSON body",
                "failure_path": "stop and capture API response",
                "action": {"type": "api.get", "path": "/items/${inputs.record_id}"},
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    },
    "desktop_form_fill": {
        **BASE_CONTRACT,
        "type": "desktop",
        "description": "Launch a desktop app, fill a form, and verify the UI state.",
        "inputs": {"app_path": "C:/Path/To/App.exe"},
        "allowed_side_effects": ["desktop_form_submit"],
        "steps": [
            {
                "id": "launch_app",
                "current_stage": "launch_desktop_app",
                "intent": "Launch the desktop app and reach the main window.",
                "preconditions": ["app path exists"],
                "postconditions": ["main window exists"],
                "proof": "window_exists check",
                "failure_path": "stop with UIA tree evidence",
                "action": {"type": "desktop.launch", "app_path": "${inputs.app_path}"},
                "success_check": [{"type": "window_exists", "value": "main"}],
            }
        ],
    },
    "browser_scrape": {
        **BASE_CONTRACT,
        "type": "browser",
        "description": "Open a page, extract visible content, and verify output.",
        "inputs": {"target_url": "https://example.com"},
        "steps": [
            {
                "id": "open_page",
                "current_stage": "open_source_page",
                "intent": "Open the source page for extraction.",
                "preconditions": ["target_url is reachable"],
                "postconditions": ["page body is visible"],
                "proof": "visible text or selector",
                "failure_path": "stop and capture browser evidence",
                "action": {"type": "browser.goto", "url": "${inputs.target_url}"},
                "success_check": [{"type": "url_contains", "value": "example"}],
            }
        ],
    },
    "reconciliation": {
        **BASE_CONTRACT,
        "type": "mixed",
        "description": "Compare source and target records and write mismatch evidence.",
        "inputs": {"source_file": "data/source.xlsx", "target_api": "https://api.example.com"},
        "allowed_side_effects": ["write_mismatch_report"],
        "steps": [
            {
                "id": "load_source",
                "current_stage": "load_source_records",
                "intent": "Load source records for comparison.",
                "preconditions": ["source file exists"],
                "postconditions": ["source rows are loaded"],
                "proof": "row_count output",
                "failure_path": "stop before target lookup",
                "action": {"type": "excel.read", "path": "${inputs.source_file}", "output": "rows"},
                "success_check": [{"type": "variable_has_value", "value": "rows"}],
            }
        ],
    },
}
