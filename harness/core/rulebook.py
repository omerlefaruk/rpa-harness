"""RPA workflow rulebook contract and audit helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    DATA = "data"
    BUSINESS = "business"
    AUTHORIZATION_CONFIG = "authorization_config"
    AUTOMATION_DEFECT = "automation_defect"
    EXTERNAL_SYSTEM = "external_system"
    SECURITY_PRIVACY = "security_privacy"
    UNKNOWN = "unknown"


@dataclass
class WorkflowRulebookContract:
    owner: str | None = None
    target_systems: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_destination: str | None = None
    system_of_record: str | None = None
    success_condition: str | None = None
    safe_test_case: str | None = None
    allowed_side_effects: list[str] = field(default_factory=list)
    rerun_policy: str | None = None
    escalation_owner: str | None = None


@dataclass
class StepRulebookContract:
    intent: str | None = None
    current_stage: str | None = None
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    proof: str | None = None
    failure_path: str | None = None


@dataclass
class RulebookAuditResult:
    score: int
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def ready_for_unattended_production(self) -> bool:
        return self.score >= 5 and not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "warnings": list(self.warnings),
            "missing_fields": list(self.missing_fields),
            "summary": self.summary,
            "ready_for_unattended_production": self.ready_for_unattended_production,
        }


SIDE_EFFECT_ACTION_TERMS = {
    "append",
    "approve",
    "checkout",
    "create",
    "delete",
    "email",
    "export",
    "finalize",
    "patch",
    "pay",
    "payment",
    "post",
    "put",
    "send",
    "submit",
    "update",
    "upload",
    "write",
}

SAFE_RETRY_ACTION_TERMS = {
    "api.get",
    "browser.goto",
    "browser.wait",
    "desktop.wait",
    "file.exists",
    "no_op",
    "read",
    "wait",
}


def action_has_side_effect(action_type: str | None) -> bool:
    if not action_type:
        return False
    normalized = action_type.lower().replace("-", "_")
    return any(term in normalized for term in SIDE_EFFECT_ACTION_TERMS)


def retry_policy_is_safe(step: dict[str, Any]) -> bool:
    action = _as_dict(step.get("action"))
    action_type = _get_text(step, "action_type") or _get_text(action, "type")
    failure_class = _normalize_failure_class(step.get("failure_class") or step.get("error_class"))
    has_retry = _has_retry_policy(step)
    if not has_retry:
        return True
    if failure_class and failure_class is not FailureClass.TRANSIENT:
        return False
    if action_has_side_effect(action_type) and not _has_side_effect_guard(step):
        return False
    return _max_attempts(step) is not None


def audit_workflow_rulebook(workflow: dict[str, Any]) -> RulebookAuditResult:
    warnings: list[str] = []
    missing_fields: list[str] = []
    present = 0
    total = 0

    for field_name in (
        "owner",
        "target_systems",
        "input_schema",
        "success_condition",
        "safe_test_case",
        "allowed_side_effects",
        "rerun_policy",
        "escalation_owner",
    ):
        total += 1
        if _has_value(workflow.get(field_name)):
            present += 1
        else:
            _record_missing(missing_fields, warnings, f"workflow.{field_name}")

    total += 1
    if _has_value(workflow.get("output_destination")) or _has_value(
        workflow.get("system_of_record")
    ):
        present += 1
    else:
        _record_missing(missing_fields, warnings, "workflow.output_destination/system_of_record")

    steps = workflow.get("steps")
    if isinstance(steps, list) and steps:
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                warnings.append(f"step[{index}] is not a mapping and cannot be audited")
                continue
            step_present, step_total = _audit_step(step, index, warnings, missing_fields)
            present += step_present
            total += step_total
            if _has_retry_policy(step) and not retry_policy_is_safe(step):
                warnings.append(f"step[{index}] has an unsafe retry policy")
    else:
        warnings.append("workflow has no auditable steps")

    score = _score(present, total)
    summary = _summary(score, missing_fields, warnings)
    return RulebookAuditResult(
        score=score,
        warnings=warnings,
        missing_fields=missing_fields,
        summary=summary,
    )


def _audit_step(
    step: dict[str, Any],
    index: int,
    warnings: list[str],
    missing_fields: list[str],
) -> tuple[int, int]:
    present = 0
    total = 0
    for field_name in ("intent", "current_stage", "preconditions", "failure_path"):
        total += 1
        if _has_value(step.get(field_name)):
            present += 1
        else:
            _record_missing(missing_fields, warnings, f"steps[{index}].{field_name}")

    total += 1
    if _has_value(step.get("postconditions")) or _has_value(step.get("success_check")):
        present += 1
    else:
        _record_missing(missing_fields, warnings, f"steps[{index}].postconditions")

    total += 1
    if _has_value(step.get("proof")) or _has_value(step.get("evidence")):
        present += 1
    else:
        _record_missing(missing_fields, warnings, f"steps[{index}].proof")

    return present, total


def _record_missing(
    missing_fields: list[str],
    warnings: list[str],
    field_name: str,
) -> None:
    missing_fields.append(field_name)
    warnings.append(f"missing rulebook field: {field_name}")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _has_retry_policy(step: dict[str, Any]) -> bool:
    if _has_value(step.get("retry_policy")) or _has_value(step.get("rerun_policy")):
        return True
    recovery = step.get("recovery")
    if isinstance(recovery, list):
        return any(_as_dict(item).get("type") == "retry" for item in recovery)
    if isinstance(recovery, dict):
        return recovery.get("type") == "retry"
    return False


def _max_attempts(step: dict[str, Any]) -> int | None:
    for key in ("max_attempts", "attempts", "retries"):
        value = step.get(key)
        if isinstance(value, int) and value > 0:
            return value

    retry_policy = step.get("retry_policy")
    if isinstance(retry_policy, dict):
        value = retry_policy.get("max_attempts") or retry_policy.get("attempts")
        if isinstance(value, int) and value > 0:
            return value
    if isinstance(retry_policy, str) and "bounded" in retry_policy.lower():
        return 1

    recovery = step.get("recovery")
    recovery_items = recovery if isinstance(recovery, list) else [recovery]
    for item in recovery_items:
        recovery_item = _as_dict(item)
        value = recovery_item.get("max_attempts") or recovery_item.get("attempts")
        if isinstance(value, int) and value > 0:
            return value
    return None


def _has_side_effect_guard(step: dict[str, Any]) -> bool:
    guard_fields = (
        "idempotency_key",
        "idempotency",
        "check_before_create",
        "duplicate_check",
        "side_effect_check",
        "verify_before_retry",
        "external_reference_id",
    )
    return any(_has_value(step.get(field_name)) for field_name in guard_fields)


def _normalize_failure_class(value: Any) -> FailureClass | None:
    if isinstance(value, FailureClass):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "authorization": FailureClass.AUTHORIZATION_CONFIG,
        "auth": FailureClass.AUTHORIZATION_CONFIG,
        "config": FailureClass.AUTHORIZATION_CONFIG,
        "configuration": FailureClass.AUTHORIZATION_CONFIG,
        "external": FailureClass.EXTERNAL_SYSTEM,
        "security": FailureClass.SECURITY_PRIVACY,
        "privacy": FailureClass.SECURITY_PRIVACY,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return FailureClass(normalized)
    except ValueError:
        return FailureClass.UNKNOWN


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _get_text(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _score(present: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(5, round((present / total) * 5)))


def _summary(score: int, missing_fields: list[str], warnings: list[str]) -> str:
    if score == 5 and not warnings:
        return "Rulebook contract is complete for the audited fields."
    if score >= 3:
        return f"Rulebook contract is partially ready with {len(missing_fields)} missing fields."
    return f"Rulebook contract is not production-ready; {len(missing_fields)} fields are missing."
