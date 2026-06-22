"""Default YAML schema validation, legacy migration, and graph helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from harness.core.ids import WORKFLOW_ID_RE, slug_id
from harness.security import SECRET_REF_RE, redact_value
from harness.verification.contract import CheckType, SUPPORTED_ACTIONS


SIDE_EFFECTS = {"none", "local_only", "external_read", "external_write", "destructive"}
SELECTOR_QUALITY = {"strong", "medium", "weak", "coordinate_fallback"}
RELIABILITY_LEVELS = {
    "api",
    "browser_dom",
    "desktop_uia",
    "desktop_win32",
    "keyboard_menu",
    "image_ocr",
    "coordinate_fallback",
    "mixed",
}
SECRET_CANARIES = (
    "RPA_SECRET_CANARY_12345",
    "fake-password-do-not-log",
    "sk-test-canary-12345",
    "Bearer rpa-canary-token",
)
def load_workflow_yaml_compat(path: str | Path) -> dict[str, Any]:
    workflow = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if int(workflow.get("schema_version") or 1) == 2:
        errors = validate_workflow_schema(workflow)["errors"]
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")
        return normalize_default_schema_to_runner(workflow)
    return workflow


def validate_workflow_schema(workflow: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(workflow, dict):
        return {"errors": ["schema: workflow must be a mapping"], "warnings": []}
    if workflow.get("schema_version") != 2:
        errors.append("schema: schema_version must be 2")
    name = workflow.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("schema: name is required")
    metadata = workflow.get("metadata") or {}
    level = metadata.get("reliability_level")
    if level and level not in RELIABILITY_LEVELS:
        errors.append(f"schema: unknown reliability_level '{level}'")
    if _contains_secret_canary(workflow):
        errors.append("security: raw secret canary value is not allowed")

    targets = workflow.get("targets") or {}
    if targets and not isinstance(targets, dict):
        errors.append("schema: targets must be a mapping")
        targets = {}
    phases = workflow.get("phases")
    if not isinstance(phases, list) or not phases:
        errors.append("schema: phases must be a non-empty list")
        phases = []

    declared_secrets = {
        str(item.get("name"))
        for item in workflow.get("secrets", []) or []
        if isinstance(item, dict) and item.get("name")
    }
    declared_inputs = set((workflow.get("inputs") or {}).keys())
    phase_ids: set[str] = set()
    step_ids: set[str] = set()
    total_steps = 0
    checked_steps = 0
    weak_selectors = []
    human_gates = []
    side_effect_counts: dict[str, int] = {}

    for phase in phases:
        if not isinstance(phase, dict):
            errors.append("schema: phase must be a mapping")
            continue
        phase_id = str(phase.get("id") or "")
        if not WORKFLOW_ID_RE.match(phase_id):
            errors.append(f"schema: invalid phase id '{phase_id}'")
        if phase_id in phase_ids:
            errors.append(f"schema: duplicate phase id '{phase_id}'")
        phase_ids.add(phase_id)
        for_each = phase.get("for_each") or {}
        if for_each:
            input_name = str(for_each.get("input") or "")
            if input_name and input_name not in declared_inputs:
                errors.append(f"schema: phase '{phase_id}' references unknown input '{input_name}'")
        for step in phase.get("steps") or []:
            total_steps += 1
            errors.extend(
                _validate_schema_step(
                    step,
                    phase_id,
                    targets,
                    declared_secrets,
                    step_ids,
                    weak_selectors,
                    human_gates,
                    side_effect_counts,
                )
            )
            if isinstance(step, dict) and step.get("success_checks"):
                checked_steps += 1

    return {
        "errors": errors,
        "warnings": warnings,
        "total_steps": total_steps,
        "steps_with_success_checks": checked_steps,
        "success_check_coverage": checked_steps / total_steps if total_steps else 0,
        "side_effect_summary": side_effect_counts,
        "weak_selectors": weak_selectors,
        "human_gates": human_gates,
    }


def _validate_schema_step(
    step: Any,
    phase_id: str,
    targets: dict[str, Any],
    declared_secrets: set[str],
    step_ids: set[str],
    weak_selectors: list[str],
    human_gates: list[str],
    side_effect_counts: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(step, dict):
        return [f"schema: phase '{phase_id}' step must be a mapping"]
    step_id = str(step.get("id") or "")
    if not WORKFLOW_ID_RE.match(step_id):
        errors.append(f"schema: invalid step id '{step_id}'")
    if step_id in step_ids:
        errors.append(f"schema: duplicate step id '{step_id}'")
    step_ids.add(step_id)

    if step.get("type") == "human_gate":
        human_gates.append(step_id)
        choices = step.get("choices") or []
        safe = step.get("default_safe_action")
        if not choices or safe not in choices:
            errors.append(f"schema: human_gate '{step_id}' requires choices and default_safe_action")
        return errors

    target = step.get("target")
    if target and str(target) not in targets:
        errors.append(f"schema: step '{step_id}' references unknown target '{target}'")
    action = step.get("action") or {}
    action_type = action.get("type") if isinstance(action, dict) else None
    if action_type not in SUPPORTED_ACTIONS:
        errors.append(f"schema: step '{step_id}' unknown action type '{action_type}'")
    checks = step.get("success_checks")
    if not isinstance(checks, list) or not checks:
        errors.append(f"schema: step '{step_id}' missing success_checks")
    else:
        valid_checks = {item.value for item in CheckType}
        for index, check in enumerate(checks):
            ctype = check.get("type") if isinstance(check, dict) else None
            if ctype not in valid_checks:
                errors.append(f"schema: step '{step_id}' check[{index}] unknown type '{ctype}'")
    side_effect = str(step.get("side_effect") or _default_side_effect(action_type))
    side_effect_counts[side_effect] = side_effect_counts.get(side_effect, 0) + 1
    if side_effect not in SIDE_EFFECTS:
        errors.append(f"schema: step '{step_id}' invalid side_effect '{side_effect}'")
    if step.get("retryable") is True and side_effect in {"external_write", "destructive"}:
        if not step.get("idempotency_key") and not step.get("validation_override"):
            errors.append(f"schema: step '{step_id}' retryable external_write requires idempotency_key")
    quality = str(step.get("selector_quality") or _selector_quality(action))
    if quality not in SELECTOR_QUALITY:
        errors.append(f"schema: step '{step_id}' invalid selector_quality '{quality}'")
    if quality in {"weak", "coordinate_fallback"}:
        weak_selectors.append(step_id)
    for secret_name in SECRET_REF_RE.findall(json.dumps(action, default=str)):
        if secret_name not in declared_secrets:
            errors.append(f"security: step '{step_id}' references undeclared secret '{secret_name}'")
    for value in _walk_values(action):
        if isinstance(value, dict) and "secret" in value and str(value["secret"]) not in declared_secrets:
            errors.append(f"security: step '{step_id}' references undeclared secret '{value['secret']}'")
    return errors


def normalize_default_schema_to_runner(workflow: dict[str, Any]) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    credentials = {
        str(item["name"]): str(item.get("env") or item["name"])
        for item in workflow.get("secrets", []) or []
        if isinstance(item, dict) and item.get("name")
    }
    for phase in workflow.get("phases") or []:
        phase_id = str(phase.get("id") or "main")
        phase_loop = phase.get("for_each")
        for raw_step in phase.get("steps") or []:
            if raw_step.get("type") == "human_gate":
                steps.append(
                    {
                        "id": raw_step["id"],
                        "description": raw_step.get("question") or raw_step["id"],
                        "phase": phase_id,
                        "action": {"type": "no_op"},
                        "allow_without_success_check": True,
                    }
                )
                continue
            step = {
                "id": raw_step["id"],
                "description": raw_step.get("name") or raw_step.get("description") or raw_step["id"],
                "phase": phase_id,
                "action": _normalize_action(raw_step.get("action") or {}),
                "success_check": raw_step.get("success_checks") or [],
            }
            if phase_loop and "for_each" not in raw_step:
                step["for_each"] = phase_loop
            for key in ("side_effect", "retryable", "idempotency_key", "record_id", "row_number", "for_each"):
                if key in raw_step:
                    step[key] = raw_step[key]
            steps.append(step)
    return {
        "id": workflow.get("id") or slug_id(workflow.get("name") or "workflow"),
        "name": workflow.get("name") or workflow.get("id") or "workflow",
        "version": str(workflow.get("version") or "2"),
        "type": _workflow_type(workflow),
        "description": workflow.get("description", ""),
        "inputs": _flatten_inputs(workflow.get("inputs") or {}),
        "credentials": credentials,
        "steps": steps,
    }


def migrate_legacy_workflow(
    source: str | Path,
    output: str | Path,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(source)
    output = Path(output)
    workflow = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for step in workflow.get("steps") or []:
        phase = str(step.get("phase") or "main")
        migrated_step = {
            "id": step.get("id"),
            "name": step.get("description") or step.get("id"),
            "action": redact_value(step.get("action") or {}),
            "success_checks": redact_value(step.get("success_check") or []),
            "side_effect": step.get("side_effect") or _default_side_effect((step.get("action") or {}).get("type")),
            "retryable": bool(step.get("retryable", False)),
        }
        for key in ("target", "idempotency_key", "record_id", "row_number", "selector_quality"):
            if key in step:
                migrated_step[key] = redact_value(step[key])
        if not step.get("side_effect"):
            warnings.append(f"step '{step.get('id')}' missing side_effect metadata")
        if not step.get("success_check"):
            warnings.append(f"step '{step.get('id')}' missing success checks")
        grouped.setdefault(phase, []).append(migrated_step)

    migrated = {
        "schema_version": 2,
        "id": workflow.get("id") or slug_id(workflow.get("name") or source.stem),
        "name": workflow.get("name") or workflow.get("id") or source.stem,
        "description": workflow.get("description", ""),
        "metadata": {"reliability_level": _reliability_from_type(workflow.get("type"))},
        "inputs": {"primary": {"type": workflow.get("type") or "mixed", "variables": redact_value(workflow.get("inputs") or {})}},
        "secrets": [
            {"name": name, "env": env, "required": True}
            for name, env in (workflow.get("credentials") or {}).items()
        ],
        "policies": {"require_success_checks": True, "retry_requires_idempotent": True, "redact_artifacts": True},
        "targets": {"default": {"type": workflow.get("type") or "mixed"}},
        "phases": [{"id": phase, "name": phase.replace("_", " ").title(), "steps": steps} for phase, steps in grouped.items()],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(redact_value(migrated), sort_keys=False), encoding="utf-8")
    report = {
        "source_file": str(source),
        "target_file": str(output),
        "fields_migrated": ["id", "name", "description", "inputs", "credentials", "steps", "success_check"],
        "warnings": warnings,
        "manual_review_required": bool(warnings),
    }
    if report_path:
        Path(report_path).write_text(_migration_report_md(report), encoding="utf-8")
    return {"status": "written", "workflow": migrated, "report": report}


def generate_workflow_graph(workflow: dict[str, Any]) -> dict[str, Any]:
    if int(workflow.get("schema_version") or 1) != 2:
        workflow = migrate_legacy_dict(workflow)
    validation = validate_workflow_schema(workflow)
    phases = []
    total_steps = 0
    external_write_steps = 0
    human_gates = 0
    weak_selectors = 0
    checked = 0
    for phase in workflow.get("phases") or []:
        graph_steps = []
        for step in phase.get("steps") or []:
            total_steps += 1
            is_gate = step.get("type") == "human_gate"
            human_gates += 1 if is_gate else 0
            checks = step.get("success_checks") or []
            checked += 1 if checks else 0
            side_effect = step.get("side_effect") or _default_side_effect((step.get("action") or {}).get("type"))
            external_write_steps += 1 if side_effect == "external_write" else 0
            quality = step.get("selector_quality") or _selector_quality(step.get("action") or {})
            weak_selectors += 1 if quality in {"weak", "coordinate_fallback"} else 0
            graph_steps.append(
                {
                    "id": step.get("id"),
                    "action_type": "human_gate" if is_gate else (step.get("action") or {}).get("type"),
                    "success_checks": [check.get("type") for check in checks if isinstance(check, dict)],
                    "side_effect": side_effect,
                    "retryable": bool(step.get("retryable", False)),
                    "selector_quality": quality,
                    "human_gate": is_gate,
                    "warnings": [error for error in validation["errors"] if f"'{step.get('id')}'" in error],
                }
            )
        phases.append({"id": phase.get("id"), "name": phase.get("name") or phase.get("id"), "steps": graph_steps})
    return {
        "workflow": workflow.get("name") or workflow.get("id"),
        "schema_version": 2,
        "phases": phases,
        "summary": {
            "total_phases": len(phases),
            "total_steps": total_steps,
            "steps_with_success_checks": checked,
            "external_write_steps": external_write_steps,
            "human_gates": human_gates,
            "weak_selectors": weak_selectors,
        },
        "validation": validation,
    }


def migrate_legacy_dict(workflow: dict[str, Any]) -> dict[str, Any]:
    phases: dict[str, list[dict[str, Any]]] = {}
    for step in workflow.get("steps") or []:
        phases.setdefault(str(step.get("phase") or "main"), []).append(
            {
                "id": step.get("id"),
                "name": step.get("description") or step.get("id"),
                "action": step.get("action") or {},
                "success_checks": step.get("success_check") or [],
                "side_effect": step.get("side_effect") or _default_side_effect((step.get("action") or {}).get("type")),
                "retryable": bool(step.get("retryable", False)),
            }
        )
    return {
        "schema_version": 2,
        "id": workflow.get("id"),
        "name": workflow.get("name") or workflow.get("id"),
        "targets": {"default": {"type": workflow.get("type") or "mixed"}},
        "phases": [{"id": phase, "steps": steps} for phase, steps in phases.items()],
    }


def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_action(value) for key, value in action.items()} if isinstance(action, dict) else action


def _flatten_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    if "primary" in inputs and isinstance(inputs["primary"], dict):
        primary = inputs["primary"]
        values = dict(primary.get("variables") or {})
        if primary.get("path"):
            values["input_file"] = primary["path"]
        return values
    return inputs


def _workflow_type(workflow: dict[str, Any]) -> str:
    targets = workflow.get("targets") or {}
    types = {str(target.get("type")) for target in targets.values() if isinstance(target, dict)}
    if len(types) == 1:
        return next(iter(types))
    return "mixed"


def _default_side_effect(action_type: Any) -> str:
    action = str(action_type or "no_op")
    if action in {"api.post", "api.put", "api.patch", "api.delete"}:
        return "external_write"
    if action.startswith(("excel.write", "excel.append")):
        return "local_only"
    if action in {"no_op"}:
        return "none"
    return "external_read" if action.startswith(("browser.", "api.", "desktop.", "excel.")) else "none"


def _selector_quality(action: Any) -> str:
    selector = action.get("selector") if isinstance(action, dict) else None
    strategy = str((selector or {}).get("strategy") or "").lower()
    if strategy in {"data-testid", "testid", "role", "label", "automation_id", "name+control_type"}:
        return "strong"
    if strategy in {
        "placeholder",
        "text",
        "id",
        "name",
        "css",
        "win32_control_id",
        "class_name",
        "class_name+control_type",
    }:
        return "medium"
    if strategy in {"xpath", "image", "ocr", "tree_path", "coordinate"}:
        return "coordinate_fallback" if strategy == "coordinate" else "weak"
    return "strong" if not selector else "weak"


def _reliability_from_type(value: Any) -> str:
    return {
        "browser": "browser_dom",
        "desktop": "desktop_uia",
        "api": "api",
        "excel": "api",
    }.get(str(value), "mixed")


def _contains_secret_canary(value: Any) -> bool:
    text = json.dumps(value, default=str)
    return any(canary in text for canary in SECRET_CANARIES)


def _walk_values(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield child
            yield from _walk_values(child)


def _migration_report_md(report: dict[str, Any]) -> str:
    warnings = "\n".join(f"- {item}" for item in report["warnings"]) or "- none"
    fields = "\n".join(f"- {item}" for item in report["fields_migrated"])
    return (
        "# YAML Legacy Migration Report\n\n"
        f"- source file: {report['source_file']}\n"
        f"- target file: {report['target_file']}\n"
        f"- manual review required: {report['manual_review_required']}\n\n"
        "## Fields Migrated\n"
        f"{fields}\n\n"
        "## Warnings\n"
        f"{warnings}\n"
    )
