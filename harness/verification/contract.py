"""
Verification contract — defines success checks for workflow steps.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from harness.security import is_sensitive_key


class CheckType(str, Enum):
    # Browser
    URL_CONTAINS = "url_contains"
    URL_EQUALS = "url_equals"
    VISIBLE_TEXT = "visible_text"
    SELECTOR_VISIBLE = "selector_visible"
    SELECTOR_HIDDEN = "selector_hidden"
    FIELD_HAS_VALUE = "field_has_value"
    DOWNLOAD_EXISTS = "download_exists"
    # Desktop
    WINDOW_EXISTS = "window_exists"
    ELEMENT_EXISTS = "element_exists"
    ELEMENT_TEXT_EQUALS = "element_text_equals"
    # API
    STATUS_CODE = "status_code"
    JSON_PATH_EQUALS = "json_path_equals"
    RESPONSE_CONTAINS = "response_contains"
    # Excel
    WORKBOOK_EXISTS = "workbook_exists"
    SHEET_EXISTS = "sheet_exists"
    CELL_EQUALS = "cell_equals"
    # Generic
    FILE_EXISTS = "file_exists"
    VARIABLE_HAS_VALUE = "variable_has_value"
    VARIABLE_EQUALS = "variable_equals"
    TEXT_CONTAINS = "text_contains"
    ALWAYS_PASS = "always_pass"


@dataclass
class SuccessCheck:
    type: CheckType
    value: Any = None
    redacted: bool = False
    selector: Optional[dict] = None
    message: str = ""

    def to_dict(self) -> dict:
        d = {"type": self.type.value, "value": self.value}
        if self.redacted:
            d["redacted"] = True
        if self.selector:
            d["selector"] = self.selector
        if self.message:
            d["message"] = self.message
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SuccessCheck":
        return cls(
            type=CheckType(data["type"]),
            value=data.get("value"),
            redacted=data.get("redacted", False),
            selector=data.get("selector"),
            message=data.get("message", ""),
        )


@dataclass
class VerificationResult:
    passed: bool
    check_type: CheckType
    expected: Any
    actual: Any
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "check_type": self.check_type.value,
            "expected": "[REDACTED]" if self.evidence.get("redacted") else self.expected,
            "actual": "[REDACTED]" if self.evidence.get("redacted") else self.actual,
            "message": self.message,
            "evidence": self.evidence,
        }


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SAFE_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
SECRET_REF_RE = re.compile(r"\$\{secrets\.([A-Za-z_][A-Za-z0-9_]*)\}")

BROWSER_ACTIONS = {
    "browser.goto",
    "browser.click",
    "browser.fill",
    "browser.get_title",
    "browser.wait_for",
    "browser.wait_for_url",
    "browser.press",
    "browser.select_option",
    "browser.check",
    "browser.uncheck",
    "browser.get_text",
}

API_ACTIONS = {
    "api.get",
    "api.post",
    "api.put",
    "api.patch",
    "api.delete",
}

DESTRUCTIVE_API_ACTIONS = {
    "api.post",
    "api.put",
    "api.patch",
    "api.delete",
}

DESKTOP_ACTIONS = {
    "desktop.launch",
    "desktop.click",
    "desktop.get_text",
    "desktop.close",
}

EXCEL_ACTIONS = {
    "excel.read",
    "excel.write",
    "excel.append_row",
}

SUPPORTED_ACTIONS = BROWSER_ACTIONS | API_ACTIONS | DESKTOP_ACTIONS | EXCEL_ACTIONS | {"no_op"}


def validate_workflow_step(step: dict) -> List[str]:
    errors = []
    if not isinstance(step, dict):
        return ["schema: step must be a mapping"]
    step_id = step.get("id", "unknown")
    action = step.get("action", {})
    action_type = action.get("type", "unknown") if isinstance(action, dict) else "unknown"

    if "id" not in step:
        errors.append("schema: step missing required field: id")
    elif not isinstance(step_id, str) or not SAFE_ID_RE.match(step_id):
        errors.append(f"schema: step id '{step_id}' must match {SAFE_ID_RE.pattern}")

    if not isinstance(action, dict):
        errors.append(f"schema: Step '{step_id}' action must be an object")
        action = {}
    elif action_type not in SUPPORTED_ACTIONS:
        errors.append(f"schema: Step '{step_id}' unknown action type '{action_type}'")

    if step.get("allow_without_success_check") and action_type != "no_op":
        errors.append(
            f"schema: Step '{step_id}' allow_without_success_check is only allowed for no_op"
        )

    output = action.get("output")
    if output is not None and (not isinstance(output, str) or not IDENTIFIER_RE.match(output)):
        errors.append(f"schema: Step '{step_id}' action.output must match {IDENTIFIER_RE.pattern}")

    errors.extend(_validate_action_fields(step_id, action_type, action))

    if "success_check" not in step:
        if step.get("allow_without_success_check") and action_type == "no_op":
            return errors
        errors.append(f"schema: Step '{step_id}' missing success_check")
    else:
        for i, check in enumerate(step["success_check"]):
            ctype = check.get("type", "")
            if not ctype or ctype not in [c.value for c in CheckType]:
                errors.append(f"schema: Step '{step_id}' check[{i}]: unknown type '{ctype}'")
                continue

            value = check.get("value")
            if ctype == CheckType.ALWAYS_PASS.value and action_type != "no_op":
                errors.append(
                    f"schema: Step '{step_id}' check[{i}]: always_pass is only allowed for no_op"
                )

            if ctype in {
                CheckType.DOWNLOAD_EXISTS.value,
                CheckType.WINDOW_EXISTS.value,
                CheckType.SHEET_EXISTS.value,
            } and not isinstance(value, str):
                errors.append(
                    f"schema: Step '{step_id}' check[{i}]: '{ctype}' requires string value"
                )

            if ctype == CheckType.JSON_PATH_EQUALS.value:
                if not isinstance(value, dict) or "path" not in value or "value" not in value:
                    errors.append(
                        f"schema: Step '{step_id}' check[{i}]: "
                        "'json_path_equals' requires value.path and value.value"
                    )

            if ctype == CheckType.CELL_EQUALS.value:
                if not isinstance(value, dict) or "cell" not in value or "value" not in value:
                    errors.append(
                        f"schema: Step '{step_id}' check[{i}]: "
                        "'cell_equals' requires value.cell and value.value"
                    )

            if ctype == CheckType.ELEMENT_TEXT_EQUALS.value:
                if isinstance(value, dict) and "value" not in value:
                    errors.append(
                        f"schema: Step '{step_id}' check[{i}]: "
                        "'element_text_equals' dict value requires key 'value'"
                    )

            if action_type.startswith("browser.") and ctype == CheckType.FIELD_HAS_VALUE.value:
                if not isinstance(check.get("selector"), dict):
                    errors.append(
                        f"schema: Step '{step_id}' check[{i}]: field_has_value requires selector"
                    )
    for i, recovery in enumerate(step.get("recovery", []) or []):
        rtype = recovery.get("type") if isinstance(recovery, dict) else None
        if rtype not in {"retry", "wait", "refresh_page"}:
            errors.append(f"schema: Step '{step_id}' recovery[{i}]: unsupported type '{rtype}'")
        if rtype == "retry" and "max_attempts" not in recovery:
            errors.append(f"schema: Step '{step_id}' recovery[{i}]: retry requires max_attempts")
        if rtype == "wait" and not ("ms" in recovery or "duration_ms" in recovery):
            errors.append(f"schema: Step '{step_id}' recovery[{i}]: wait requires ms")
    return errors


def validate_workflow(workflow: dict) -> List[str]:
    errors = []
    if not isinstance(workflow, dict):
        return ["schema: workflow must be a mapping"]

    required = ["id", "name", "version", "type", "steps"]
    for required_field in required:
        if required_field not in workflow:
            errors.append(f"schema: Workflow missing required field: {required_field}")

    workflow_id = workflow.get("id")
    if workflow_id is not None and (
        not isinstance(workflow_id, str) or not SAFE_ID_RE.match(workflow_id)
    ):
        errors.append(f"schema: workflow id '{workflow_id}' must match {SAFE_ID_RE.pattern}")

    workflow_type = workflow.get("type")
    if workflow_type not in {"browser", "api", "desktop", "excel", "mixed"}:
        errors.append(f"schema: Workflow type '{workflow_type}' is not supported")

    credentials = workflow.get("credentials", {}) or {}
    if credentials and not isinstance(credentials, dict):
        errors.append("schema: credentials must be a mapping")
        credentials = {}

    inputs = workflow.get("inputs", {}) or {}
    if isinstance(inputs, dict):
        for path, value in _walk_values(inputs, prefix="inputs"):
            if isinstance(value, str) and SECRET_REF_RE.search(value):
                errors.append(f"security: secrets are not allowed in inputs ({path})")
    elif "inputs" in workflow:
        errors.append("schema: inputs must be a mapping")

    if "steps" in workflow:
        if not isinstance(workflow["steps"], list):
            errors.append("schema: steps must be a list")
            return errors

        seen_step_ids = set()
        for step in workflow["steps"]:
            step_id = step.get("id", "unknown") if isinstance(step, dict) else "unknown"
            if step_id in seen_step_ids:
                errors.append(f"schema: duplicate step id '{step_id}'")
            seen_step_ids.add(step_id)

            errors.extend(validate_workflow_step(step))
            if isinstance(step, dict):
                errors.extend(_validate_workflow_action_rules(workflow, step, credentials))
                errors.extend(_validate_security_literals(step))
    return errors


def _validate_action_fields(step_id: str, action_type: str, action: dict) -> List[str]:
    errors: List[str] = []
    if action_type == "browser.goto":
        _require(action, "url", step_id, action_type, errors)
    elif action_type in {
        "browser.click",
        "browser.check",
        "browser.uncheck",
        "browser.wait_for",
        "browser.get_text",
    }:
        _require_selector(action, step_id, action_type, errors)
        if action_type == "browser.get_text" and not action.get("output"):
            errors.append(f"schema: Step '{step_id}' {action_type} requires action.output")
    elif action_type == "browser.fill":
        _require_selector(action, step_id, action_type, errors)
        _require(action, "value", step_id, action_type, errors)
    elif action_type == "browser.select_option":
        _require_selector(action, step_id, action_type, errors)
        _require(action, "value", step_id, action_type, errors)
    elif action_type == "browser.press":
        _require(action, "key", step_id, action_type, errors)
    elif action_type == "browser.wait_for_url":
        if not action.get("url") and not action.get("value"):
            errors.append(f"schema: Step '{step_id}' {action_type} requires 'url' or 'value'")
    elif action_type in API_ACTIONS:
        if not action.get("url") and not action.get("path"):
            errors.append(f"schema: Step '{step_id}' {action_type} requires 'url' or 'path'")
        if "data" in action:
            errors.append(
                f"schema: Step '{step_id}' {action_type} supports json_data only, not data"
            )
    elif action_type == "desktop.launch":
        if not action.get("app_path") and not action.get("path"):
            errors.append(f"schema: Step '{step_id}' {action_type} requires 'app_path' or 'path'")
    elif action_type in {"desktop.click", "desktop.get_text"}:
        _require_selector(action, step_id, action_type, errors)
        if action_type == "desktop.get_text" and not action.get("output"):
            errors.append(f"schema: Step '{step_id}' {action_type} requires action.output")
    elif action_type in EXCEL_ACTIONS:
        if not action.get("path") and not action.get("file_path"):
            errors.append(f"schema: Step '{step_id}' {action_type} requires 'path' or 'file_path'")
        if action_type == "excel.write" and not (
            action.get("cell") or action.get("headers") or action.get("rows")
        ):
            errors.append(
                f"schema: Step '{step_id}' {action_type} requires 'cell' or rows/headers"
            )
        if action_type == "excel.append_row" and not (
            action.get("row_data") or action.get("mapping")
        ):
            errors.append(
                f"schema: Step '{step_id}' {action_type} requires 'row_data' or 'mapping'"
            )
    return errors


def _validate_workflow_action_rules(workflow: dict, step: dict, credentials: dict) -> List[str]:
    errors: List[str] = []
    workflow_type = workflow.get("type")
    step_id = step.get("id", "unknown")
    action = step.get("action", {}) or {}
    action_type = action.get("type", "unknown")

    if workflow_type == "browser" and not (
        action_type.startswith("browser.") or action_type == "no_op"
    ):
        errors.append(f"schema: browser workflow cannot contain action '{action_type}'")
    if workflow_type == "api" and not (action_type.startswith("api.") or action_type == "no_op"):
        errors.append(f"schema: api workflow cannot contain action '{action_type}'")
    if workflow_type == "desktop" and not (
        action_type.startswith("desktop.") or action_type == "no_op"
    ):
        errors.append(f"schema: desktop workflow cannot contain action '{action_type}'")
    if workflow_type == "excel" and not (
        action_type.startswith("excel.") or action_type == "no_op"
    ):
        errors.append(f"schema: excel workflow cannot contain action '{action_type}'")

    if action_type in DESTRUCTIVE_API_ACTIONS and workflow.get("allow_destructive") is not True:
        errors.append(
            f"security: Step '{step_id}' {action_type} requires workflow allow_destructive: true"
        )

    for path, value in _walk_values(action, prefix=f"steps.{step_id}.action"):
        if isinstance(value, str):
            for secret_name in SECRET_REF_RE.findall(value):
                if secret_name not in credentials:
                    errors.append(
                        f"security: Step '{step_id}' references undeclared secret '{secret_name}'"
                    )
            if path.endswith(".url") or path.endswith(".path"):
                if SECRET_REF_RE.search(value):
                    errors.append(f"security: Step '{step_id}' cannot use secrets in URL/path")

    return errors


def _validate_security_literals(step: dict) -> List[str]:
    errors: List[str] = []
    step_id = step.get("id", "unknown")
    action = step.get("action", {}) or {}
    for path, value in _walk_values(action, prefix=f"steps.{step_id}.action"):
        key = path.rsplit(".", 1)[-1]
        if is_sensitive_key(key) and isinstance(value, str):
            if value and not SECRET_REF_RE.search(value):
                errors.append(f"security: Step '{step_id}' has literal sensitive value at {path}")
    return errors


def _require(action: dict, field: str, step_id: str, action_type: str, errors: List[str]):
    if field not in action or action.get(field) in (None, ""):
        errors.append(f"schema: Step '{step_id}' {action_type} requires '{field}'")


def _require_selector(action: dict, step_id: str, action_type: str, errors: List[str]):
    if not isinstance(action.get("selector"), dict):
        errors.append(f"schema: Step '{step_id}' {action_type} requires selector")


def _walk_values(value: Any, prefix: str) -> List[tuple[str, Any]]:
    items: List[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            items.append((child_path, child))
            items.extend(_walk_values(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{prefix}[{index}]"
            items.append((child_path, child))
            items.extend(_walk_values(child, child_path))
    return items
