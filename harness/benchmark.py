from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkExpected:
    workflow_validates: bool
    run_succeeds: bool
    required_artifacts: list[str]


@dataclass(frozen=True)
class BenchmarkLimits:
    max_tool_calls: int | None = None
    max_wall_seconds: float | None = None


@dataclass(frozen=True)
class BenchmarkRunner:
    command: list[str]


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    kind: str
    prompt: str
    fixture: Path
    runner: BenchmarkRunner
    expected: BenchmarkExpected
    limits: BenchmarkLimits
    path: Path


@dataclass(frozen=True)
class BenchmarkResult:
    run_id: str
    task_id: str
    trial: int
    success: bool
    accuracy_score: float
    wall_seconds: float
    tool_calls: int | None
    input_tokens: int | None
    output_tokens: int | None
    retries: int
    evidence_complete: bool
    side_effects: bool
    loop_detected: bool
    notes: str


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _require_dict(data: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: missing object field {key!r}")
    return value


def _require_list(data: dict[str, Any], key: str, path: Path) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{path}: missing list field {key!r}")
    return value


def _require_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path}: missing string field {key!r}")
    return value


def load_tasks(tasks_dir: Path) -> list[BenchmarkTask]:
    if not tasks_dir.exists():
        raise ValueError(f"Tasks directory does not exist: {tasks_dir}")

    tasks: list[BenchmarkTask] = []
    for path in sorted(tasks_dir.glob("*.json")):
        raw = _read_json(path)
        expected_raw = _require_dict(raw, "expected", path)
        runner_raw = _require_dict(raw, "runner", path)
        command = _require_list(runner_raw, "command", path)
        required_artifacts = _require_list(expected_raw, "required_artifacts", path)
        limits_raw = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}

        if not all(isinstance(part, str) and part for part in command):
            raise ValueError(f"{path}: runner.command must be non-empty strings")
        if not all(isinstance(item, str) and item for item in required_artifacts):
            raise ValueError(f"{path}: expected.required_artifacts must be non-empty strings")

        tasks.append(
            BenchmarkTask(
                id=_require_str(raw, "id", path),
                kind=_require_str(raw, "kind", path),
                prompt=_require_str(raw, "prompt", path),
                fixture=Path(_require_str(raw, "fixture", path)),
                runner=BenchmarkRunner(command=list(command)),
                expected=BenchmarkExpected(
                    workflow_validates=bool(expected_raw.get("workflow_validates")),
                    run_succeeds=bool(expected_raw.get("run_succeeds")),
                    required_artifacts=list(required_artifacts),
                ),
                limits=BenchmarkLimits(
                    max_tool_calls=limits_raw.get("max_tool_calls")
                    if isinstance(limits_raw.get("max_tool_calls"), int)
                    else None,
                    max_wall_seconds=limits_raw.get("max_wall_seconds")
                    if isinstance(limits_raw.get("max_wall_seconds"), (int, float))
                    else None,
                ),
                path=path,
            )
        )

    if not tasks:
        raise ValueError(f"No benchmark task JSON files found in {tasks_dir}")
    return tasks


def _mean(values: list[int | float]) -> float | None:
    return round(float(statistics.mean(values)), 4) if values else None


def summarize_results(results: list[BenchmarkResult]) -> dict[str, Any]:
    total_tokens = [
        result.input_tokens + result.output_tokens
        for result in results
        if result.input_tokens is not None and result.output_tokens is not None
    ]
    return {
        "tasks": len(results),
        "pass_rate": round(sum(1 for result in results if result.success) / len(results), 4)
        if results
        else 0.0,
        "mean_wall_seconds": _mean([result.wall_seconds for result in results]),
        "mean_tool_calls": _mean(
            [result.tool_calls for result in results if result.tool_calls is not None]
        ),
        "mean_total_tokens": _mean(total_tokens),
        "evidence_completeness_rate": round(
            sum(1 for result in results if result.evidence_complete) / len(results), 4
        )
        if results
        else 0.0,
        "side_effect_count": sum(1 for result in results if result.side_effects),
        "loop_count": sum(1 for result in results if result.loop_detected),
    }
