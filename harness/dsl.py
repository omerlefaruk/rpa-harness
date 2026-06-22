"""Tiny Robot-inspired DSL compiler for deterministic YAML workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_SECTION_RE = re.compile(r"^\*\*\*\s+(.+?)\s+\*\*\*$")
_CELL_RE = re.compile(r"\s{2,}")
_VAR_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_VAR_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
_ALLOWED_SECTIONS = {"settings", "variables", "tasks"}
_ACTION_KEYWORDS = {"Open Browser"}
_VERIFY_KEYWORDS = {"Verify Url Contains", "Verify File Exists"}


@dataclass(frozen=True)
class DslStep:
    keyword: str
    args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DslTask:
    name: str
    steps: list[DslStep] = field(default_factory=list)


@dataclass(frozen=True)
class DslDocument:
    name: str = ""
    tags: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    tasks: list[DslTask] = field(default_factory=list)


def parse_dsl(source: str) -> DslDocument:
    section = ""
    name = ""
    tags: list[str] = []
    variables: dict[str, str] = {}
    tasks: list[DslTask] = []
    current_task: DslTask | None = None

    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        match = _SECTION_RE.match(line.strip())
        if match:
            section = match.group(1).strip().lower()
            if section not in _ALLOWED_SECTIONS:
                raise ValueError(f"Unknown DSL section on line {line_number}: {match.group(1).strip()}")
            current_task = None
            continue

        if not section:
            raise ValueError(f"DSL content before section on line {line_number}")

        cells = [cell.strip() for cell in _CELL_RE.split(line.strip()) if cell.strip()]
        if section == "settings":
            key = cells[0]
            value = cells[1] if len(cells) > 1 else ""
            if key == "Name":
                name = value
            elif key == "Tag" and value:
                tags.append(value)
            else:
                raise ValueError(f"Unknown DSL setting on line {line_number}: {key}")
        elif section == "variables":
            if len(cells) < 2:
                raise ValueError(f"Invalid DSL variable on line {line_number}")
            var_match = _VAR_RE.match(cells[0])
            if not var_match:
                raise ValueError(f"Invalid DSL variable name on line {line_number}: {cells[0]}")
            variables[var_match.group(1)] = cells[1]
        elif section == "tasks":
            if raw_line[:1].isspace():
                if current_task is None:
                    raise ValueError(f"DSL step without task on line {line_number}")
                current_task.steps.append(DslStep(cells[0], cells[1:]))
            else:
                current_task = DslTask(line.strip())
                tasks.append(current_task)

    if not tasks:
        raise ValueError("DSL must define at least one task")
    return DslDocument(name=name or tasks[0].name, tags=tags, variables=variables, tasks=tasks)


def compile_dsl_to_workflow(document: DslDocument) -> dict[str, Any]:
    phases = []
    for task in document.tasks:
        phases.append({"id": _slug(task.name), "name": task.name, "steps": _compile_task(document, task)})

    return {
        "schema_version": 2,
        "id": _slug(document.name),
        "name": document.name,
        "description": "Compiled from tiny .rpa DSL.",
        "metadata": {
            "owner": "ops",
            "tags": document.tags,
            "reliability_level": "browser_dom",
        },
        "policies": {
            "require_success_checks": True,
            "retry_requires_idempotent": True,
            "redact_artifacts": True,
        },
        "targets": {"portal": {"type": "browser"}},
        "phases": phases,
    }


def _compile_task(document: DslDocument, task: DslTask) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    index = 0
    while index < len(task.steps):
        step = task.steps[index]
        _validate_keyword(step)
        if step.keyword in _ACTION_KEYWORDS:
            if index + 1 >= len(task.steps) or task.steps[index + 1].keyword not in _VERIFY_KEYWORDS:
                raise ValueError(f"{step.keyword} must be followed by a verification")
            verify = task.steps[index + 1]
            _validate_keyword(verify)
            steps.append(_compile_action_step(document, step, verify, len(steps) + 1))
            index += 2
            continue
        steps.append(_compile_verify_step(document, step, len(steps) + 1))
        index += 1
    return steps


def _validate_keyword(step: DslStep) -> None:
    if step.keyword not in _ACTION_KEYWORDS | _VERIFY_KEYWORDS:
        raise ValueError(f"Unknown DSL keyword: {step.keyword}")


def _compile_action_step(
    document: DslDocument,
    step: DslStep,
    verify: DslStep,
    number: int,
) -> dict[str, Any]:
    if step.keyword == "Open Browser":
        _require_args(step, 1)
        return {
            "id": f"step_{number}_open_browser",
            "name": "Open Browser",
            "target": "portal",
            "action": {"type": "browser.goto", "url": _resolve(step.args[0], document.variables)},
            "success_checks": [_compile_check(document, verify)],
            "side_effect": "external_read",
            "retryable": False,
        }
    raise ValueError(f"Unknown DSL keyword: {step.keyword}")


def _compile_verify_step(document: DslDocument, step: DslStep, number: int) -> dict[str, Any]:
    return {
        "id": f"step_{number}_{_slug(step.keyword)}",
        "name": step.keyword,
        "action": {"type": "no_op"},
        "success_checks": [_compile_check(document, step)],
        "side_effect": "none",
        "retryable": False,
    }


def _compile_check(document: DslDocument, step: DslStep) -> dict[str, Any]:
    _require_args(step, 1)
    value = _resolve(step.args[0], document.variables)
    if step.keyword == "Verify Url Contains":
        return {"type": "url_contains", "value": value}
    if step.keyword == "Verify File Exists":
        return {"type": "file_exists", "value": value}
    raise ValueError(f"Unknown DSL keyword: {step.keyword}")


def _resolve(value: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ValueError(f"Unknown DSL variable: {name}")
        return variables[name]

    return _VAR_REF_RE.sub(replace, value)


def _require_args(step: DslStep, count: int) -> None:
    if len(step.args) != count:
        raise ValueError(f"{step.keyword} expects {count} argument(s)")


def _slug(value: str) -> str:
    slug = _SAFE_ID_RE.sub("_", value.strip()).strip("_").lower()
    return slug or "workflow"
