"""
Verification contract — defines success checks for workflow steps.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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


def validate_workflow_step(step: dict) -> List[str]:
    errors = []
    if "success_check" not in step:
        action_type = step.get("action", {}).get("type", "unknown")
        if step.get("allow_without_success_check") and action_type == "no_op":
            return []
        errors.append(f"Step '{step.get('id', 'unknown')}' missing success_check")
    else:
        for i, check in enumerate(step["success_check"]):
            ctype = check.get("type", "")
            if not ctype or ctype not in [c.value for c in CheckType]:
                errors.append(f"Step '{step['id']}' check[{i}]: unknown type '{ctype}'")
    return errors


def validate_workflow(workflow: dict) -> List[str]:
    errors = []
    required = ["id", "name", "version", "type", "steps"]
    for field in required:
        if field not in workflow:
            errors.append(f"Workflow missing required field: {field}")
    if "steps" in workflow:
        for step in workflow["steps"]:
            errors.extend(validate_workflow_step(step))
    return errors
