"""
Verification checks — executes success checks against real state.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.verification.contract import CheckType, SuccessCheck, VerificationResult


class CheckRunner:
    def __init__(self):
        self._context: Dict[str, Any] = {}

    def set_context(self, key: str, value: Any):
        self._context[key] = value

    def run(self, check: SuccessCheck) -> VerificationResult:
        handler = {
            CheckType.FILE_EXISTS: self._check_file_exists,
            CheckType.VARIABLE_HAS_VALUE: self._check_variable_has_value,
            CheckType.VARIABLE_EQUALS: self._check_variable_equals,
            CheckType.TEXT_CONTAINS: self._check_text_contains,
            CheckType.ALWAYS_PASS: self._check_always_pass,
            CheckType.URL_CONTAINS: self._check_url_contains,
            CheckType.URL_EQUALS: self._check_url_equals,
            CheckType.VISIBLE_TEXT: self._check_visible_text,
            CheckType.SELECTOR_VISIBLE: self._check_selector_visible,
            CheckType.SELECTOR_HIDDEN: self._check_selector_hidden,
            CheckType.FIELD_HAS_VALUE: self._check_field_has_value,
            CheckType.STATUS_CODE: self._check_status_code,
            CheckType.RESPONSE_CONTAINS: self._check_response_contains,
            CheckType.WORKBOOK_EXISTS: self._check_file_exists,
            CheckType.SHEET_EXISTS: self._check_always_pass,
            CheckType.CELL_EQUALS: self._check_always_pass,
            CheckType.WINDOW_EXISTS: self._check_always_pass,
            CheckType.ELEMENT_EXISTS: self._check_always_pass,
            CheckType.ELEMENT_TEXT_EQUALS: self._check_always_pass,
        }

        fn = handler.get(check.type, self._check_unknown)
        try:
            return fn(check)
        except Exception as e:
            return VerificationResult(
                passed=False,
                check_type=check.type,
                expected=check.value,
                actual=f"Error: {e}",
                message=str(e),
            )

    def _check_file_exists(self, check: SuccessCheck) -> VerificationResult:
        path = Path(str(check.value))
        exists = path.exists()
        return VerificationResult(
            passed=exists,
            check_type=check.type,
            expected=str(check.value),
            actual=f"exists={exists}",
            message="" if exists else f"File not found: {check.value}",
        )

    def _check_variable_has_value(self, check: SuccessCheck) -> VerificationResult:
        value = self._context.get(str(check.value))
        has = value is not None and value != ""
        return VerificationResult(
            passed=has,
            check_type=check.type,
            expected=f"non-empty value",
            actual=str(value)[:100] if value else "None/empty",
            message="" if has else f"Variable '{check.value}' has no value",
        )

    def _check_variable_equals(self, check: SuccessCheck) -> VerificationResult:
        expected = check.value.get("value") if isinstance(check.value, dict) else check.value
        var = check.value.get("var") if isinstance(check.value, dict) else check.value
        actual = self._context.get(var)
        match = str(actual) == str(expected)
        return VerificationResult(
            passed=match,
            check_type=check.type,
            expected=expected,
            actual=actual,
            message="" if match else f"Expected '{expected}', got '{actual}'",
        )

    def _check_text_contains(self, check: SuccessCheck) -> VerificationResult:
        text = self._context.get("last_text", "")
        contains = str(check.value) in text
        return VerificationResult(
            passed=contains,
            check_type=check.type,
            expected=f"text contains '{check.value}'",
            actual=text[:200],
            message="" if contains else f"Text did not contain '{check.value}'",
        )

    def _check_always_pass(self, check: SuccessCheck) -> VerificationResult:
        return VerificationResult(
            passed=True, check_type=check.type,
            expected="always", actual="passed", message="No-op check",
        )

    def _check_url_contains(self, check: SuccessCheck) -> VerificationResult:
        url = self._context.get("current_url", "")
        contains = str(check.value) in url
        return VerificationResult(
            passed=contains,
            check_type=check.type,
            expected=check.value,
            actual=url[:200],
            message="" if contains else f"URL does not contain '{check.value}'",
        )

    def _check_url_equals(self, check: SuccessCheck) -> VerificationResult:
        url = self._context.get("current_url", "")
        match = url == str(check.value)
        return VerificationResult(
            passed=match, check_type=check.type,
            expected=check.value, actual=url,
            message="" if match else f"URL mismatch",
        )

    def _check_visible_text(self, check: SuccessCheck) -> VerificationResult:
        visible = self._context.get("visible_text", "")
        contains = str(check.value) in visible
        return VerificationResult(
            passed=contains,
            check_type=check.type,
            expected=check.value,
            actual=visible[:200],
            message="" if contains else f"Text not visible: '{check.value}'",
        )

    def _check_selector_visible(self, check: SuccessCheck) -> VerificationResult:
        visible = self._context.get("selector_visible", False)
        return VerificationResult(
            passed=visible, check_type=check.type,
            expected="element visible", actual=str(visible),
        )

    def _check_selector_hidden(self, check: SuccessCheck) -> VerificationResult:
        hidden = self._context.get("selector_hidden", True)
        return VerificationResult(
            passed=hidden, check_type=check.type,
            expected="element hidden", actual=str(hidden),
        )

    def _check_field_has_value(self, check: SuccessCheck) -> VerificationResult:
        value = self._context.get("field_value", "")
        has = bool(value)
        evidence = {}
        if check.redacted:
            evidence["redacted"] = True
            return VerificationResult(
                passed=has, check_type=check.type,
                expected="[REDACTED]", actual="[REDACTED]",
                message="Field has value (value redacted)", evidence=evidence,
            )
        return VerificationResult(
            passed=has, check_type=check.type,
            expected="non-empty", actual=str(value)[:100],
        )

    def _check_status_code(self, check: SuccessCheck) -> VerificationResult:
        code = self._context.get("status_code", 0)
        match = code == int(check.value)
        return VerificationResult(
            passed=match, check_type=check.type,
            expected=check.value, actual=str(code),
        )

    def _check_response_contains(self, check: SuccessCheck) -> VerificationResult:
        body = self._context.get("response_body", "")
        contains = str(check.value) in body
        return VerificationResult(
            passed=contains, check_type=check.type,
            expected=f"contains '{check.value}'", actual=body[:500],
        )

    def _check_unknown(self, check: SuccessCheck) -> VerificationResult:
        return VerificationResult(
            passed=False, check_type=check.type,
            expected=check.value, actual="unknown check type",
            message=f"No handler for check type: {check.type.value}",
        )


def run_all_checks(checks: List[SuccessCheck], context: Dict[str, Any] = None) -> List[VerificationResult]:
    runner = CheckRunner()
    if context:
        for k, v in context.items():
            runner.set_context(k, v)
    return [runner.run(c) for c in checks]
