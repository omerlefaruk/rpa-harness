"""Deterministic execution plan for YAML workflows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionUnit:
    step: dict[str, Any]
    phase: str
    record: Any = None


@dataclass(frozen=True)
class ExecutionPlan:
    units: list[ExecutionUnit]

    @property
    def steps(self) -> list[dict[str, Any]]:
        return [unit.step for unit in self.units]

    def summary(self) -> dict[str, Any]:
        phases = sorted({unit.phase for unit in self.units})
        return {
            "total_units": len(self.units),
            "total_phases": len(phases),
            "record_units": sum(1 for unit in self.units if unit.record is not None),
            "phases": phases,
        }


def build_execution_plan(
    workflow: dict[str, Any],
    *,
    inputs: dict[str, Any] | None = None,
    phase: str | None = None,
    only_record: str | None = None,
) -> ExecutionPlan:
    inputs = inputs or workflow.get("inputs", {}) or {}
    units: list[ExecutionUnit] = []
    for raw_step in workflow.get("steps", []) or []:
        if not isinstance(raw_step, dict):
            continue
        step_phase = step_phase_id(raw_step)
        if phase and step_phase != phase:
            continue
        loop = raw_step.get("for_each")
        if isinstance(loop, dict) and loop.get("input"):
            units.extend(_loop_units(raw_step, step_phase, loop, inputs, only_record))
            continue
        if only_record and str(raw_step.get("record_id")) != str(only_record):
            continue
        units.append(ExecutionUnit(step=deepcopy(raw_step), phase=step_phase))
    return ExecutionPlan(units)


def step_phase_id(step: dict[str, Any]) -> str:
    return str(step.get("phase") or step.get("current_stage") or "default")


def _loop_units(
    raw_step: dict[str, Any],
    phase: str,
    loop: dict[str, Any],
    inputs: dict[str, Any],
    only_record: str | None,
) -> list[ExecutionUnit]:
    records = _records(inputs.get(str(loop["input"])))
    record_id_key = str(loop.get("record_id") or "id")
    units: list[ExecutionUnit] = []
    for index, record in enumerate(records, start=1):
        record_id = _record_id(record, record_id_key, index)
        if only_record and str(record_id) != str(only_record):
            continue
        step = deepcopy(raw_step)
        step.pop("for_each", None)
        step["record_id"] = record_id
        step.setdefault("row_number", index)
        step["_record"] = record
        units.append(ExecutionUnit(step=step, phase=phase, record=record))
    return units


def _records(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("records", "rows"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _record_id(record: Any, key: str, index: int) -> str:
    if isinstance(record, dict) and record.get(key) is not None:
        return str(record[key])
    return str(index)
