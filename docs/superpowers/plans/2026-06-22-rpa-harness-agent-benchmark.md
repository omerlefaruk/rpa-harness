# RPA Harness Agent Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first lean rpa-harness benchmark runner for agent-assisted workflow build/repair loops, measuring success, speed, tool calls, tokens, retries, side effects, loop detection, and evidence completeness.

**Architecture:** Add one stdlib-only module, `harness/benchmark.py`, runnable with `python -m harness.benchmark`. Tasks are JSON files. Each task executes an explicit argv command that writes `attempt.json`; the runner scores that attempt against required run artifacts and writes `results.jsonl` plus `summary.json`.

**Tech Stack:** Python stdlib (`argparse`, `dataclasses`, `json`, `pathlib`, `statistics`, `subprocess`, `time`), pytest, existing rpa-harness artifact files.

---

## File structure

- Create: `harness/benchmark.py` — task loading, command execution, deterministic scoring, JSONL/summary writing, CLI entry point.
- Create: `tests/test_benchmark.py` — loader, scoring, summary, and CLI smoke tests using temporary fixtures.
- Create: `benchmarks/README.md` — tiny operator guide for running the benchmark and reading results.
- Create: `benchmarks/fixtures/fake_agent.py` — deterministic local fixture command for the first benchmark suite.
- Create: `benchmarks/tasks/browser_happy_path.json` — happy-path lane task card.
- Create: `benchmarks/tasks/browser_selector_repair.json` — repair lane task card.
- Create: `benchmarks/tasks/invalid_missing_success_check.json` — safety/validation lane task card.
- Modify: `docs/okf/interfaces/cli.md` — document the benchmark command.
- Modify: `docs/okf/system/rpa-harness.md` — document the benchmark directory as a lightweight evidence consumer.

---

### Task 1: Add benchmark task schema and summary math

**Files:**
- Create: `harness/benchmark.py`
- Create: `tests/test_benchmark.py`

- [ ] **Step 1: Write failing loader and summary tests**

Create `tests/test_benchmark.py` with:

```python
import json
from pathlib import Path

import pytest

from harness.benchmark import BenchmarkResult, load_tasks, summarize_results


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def task_card(task_id: str, fixture: str = "benchmarks/fixtures/fake") -> dict:
    return {
        "id": task_id,
        "kind": "agent_workflow_build",
        "prompt": "Build and run the workflow from this fixture.",
        "fixture": fixture,
        "runner": {
            "command": ["{python}", "benchmarks/fixtures/fake_agent.py", "{task_json}", "{attempt_dir}"]
        },
        "expected": {
            "workflow_validates": True,
            "run_succeeds": True,
            "required_artifacts": ["run_manifest.json", "timeline.jsonl", "report.html"],
        },
        "limits": {"max_tool_calls": 40, "max_wall_seconds": 600},
    }


def test_load_tasks_reads_sorted_task_cards(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    write_json(tasks_dir / "b.json", task_card("b_task"))
    write_json(tasks_dir / "a.json", task_card("a_task"))

    tasks = load_tasks(tasks_dir)

    assert [task.id for task in tasks] == ["a_task", "b_task"]
    assert tasks[0].expected.required_artifacts == ["run_manifest.json", "timeline.jsonl", "report.html"]


def test_load_tasks_rejects_missing_required_fields(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    write_json(tasks_dir / "bad.json", {"id": "bad"})

    with pytest.raises(ValueError, match="bad.json"):
        load_tasks(tasks_dir)


def test_summarize_results_aggregates_core_metrics() -> None:
    results = [
        BenchmarkResult("bench-1", "a", 1, True, 1.0, 2.0, 10, 100, 20, 0, True, False, False, ""),
        BenchmarkResult("bench-1", "b", 1, False, 0.0, 4.0, None, None, None, 2, False, True, True, "failed"),
    ]

    summary = summarize_results(results)

    assert summary["tasks"] == 2
    assert summary["pass_rate"] == 0.5
    assert summary["mean_wall_seconds"] == 3.0
    assert summary["mean_tool_calls"] == 10.0
    assert summary["mean_total_tokens"] == 120.0
    assert summary["evidence_completeness_rate"] == 0.5
    assert summary["side_effect_count"] == 1
    assert summary["loop_count"] == 1
```

- [ ] **Step 2: Run the test and verify it fails**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q
```

Expected: FAIL because `harness.benchmark` does not exist.

- [ ] **Step 3: Implement the schema and summary functions**

Create `harness/benchmark.py` with:

```python
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
        "mean_tool_calls": _mean([result.tool_calls for result in results if result.tool_calls is not None]),
        "mean_total_tokens": _mean(total_tokens),
        "evidence_completeness_rate": round(
            sum(1 for result in results if result.evidence_complete) / len(results), 4
        )
        if results
        else 0.0,
        "side_effect_count": sum(1 for result in results if result.side_effects),
        "loop_count": sum(1 for result in results if result.loop_detected),
    }
```

- [ ] **Step 4: Run the test and verify it passes**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q
```

Expected: PASS for the three tests.

- [ ] **Step 5: Commit the schema slice**

```powershell
git add harness/benchmark.py tests/test_benchmark.py
git commit -m "feat: add benchmark task schema"
```

---

### Task 2: Score attempts from existing run artifacts

**Files:**
- Modify: `harness/benchmark.py`
- Modify: `tests/test_benchmark.py`

- [ ] **Step 1: Add failing scoring tests**

Append to `tests/test_benchmark.py`:

```python
from harness.benchmark import score_attempt


def make_task(tmp_path: Path, required_artifacts: list[str]) -> object:
    tasks_dir = tmp_path / "tasks"
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    data = task_card("score_task", str(fixture))
    data["expected"]["required_artifacts"] = required_artifacts
    write_json(tasks_dir / "score.json", data)
    return load_tasks(tasks_dir)[0]


def write_run_artifacts(run_dir: Path, names: list[str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (run_dir / name).write_text("{}" if name.endswith(".json") else "ok", encoding="utf-8")


def test_score_attempt_passes_when_expected_state_and_artifacts_exist(tmp_path: Path) -> None:
    task = make_task(tmp_path, ["run_manifest.json", "timeline.jsonl", "report.html"])
    run_dir = tmp_path / "run"
    write_run_artifacts(run_dir, ["run_manifest.json", "timeline.jsonl", "report.html"])
    attempt = {
        "workflow_validates": True,
        "run_succeeds": True,
        "run_dir": str(run_dir),
        "metrics": {"tool_calls": 5, "input_tokens": 100, "output_tokens": 25},
        "retries": 1,
        "side_effects": False,
        "loop_detected": False,
    }

    result = score_attempt("bench-1", task, 1, 1.5, attempt)

    assert result.success is True
    assert result.accuracy_score == 1.0
    assert result.evidence_complete is True
    assert result.tool_calls == 5


def test_score_attempt_half_scores_valid_workflow_with_failed_run(tmp_path: Path) -> None:
    task = make_task(tmp_path, ["run_manifest.json"])
    run_dir = tmp_path / "run"
    write_run_artifacts(run_dir, ["run_manifest.json"])
    attempt = {"workflow_validates": True, "run_succeeds": False, "run_dir": str(run_dir), "metrics": {}}

    result = score_attempt("bench-1", task, 1, 2.0, attempt)

    assert result.success is False
    assert result.accuracy_score == 0.5
    assert result.evidence_complete is True
    assert result.tool_calls is None


def test_score_attempt_fails_when_required_artifact_is_missing(tmp_path: Path) -> None:
    task = make_task(tmp_path, ["run_manifest.json", "report.html"])
    run_dir = tmp_path / "run"
    write_run_artifacts(run_dir, ["run_manifest.json"])
    attempt = {"workflow_validates": True, "run_succeeds": True, "run_dir": str(run_dir), "metrics": {}}

    result = score_attempt("bench-1", task, 1, 2.0, attempt)

    assert result.success is False
    assert result.accuracy_score == 0.0
    assert result.evidence_complete is False
    assert "missing artifacts" in result.notes
```

- [ ] **Step 2: Run the scoring tests and verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q
```

Expected: FAIL because `score_attempt` does not exist.

- [ ] **Step 3: Add scoring code**

Append to `harness/benchmark.py`:

```python
def _as_int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None


def _required_artifacts_exist(run_dir: Path, required_artifacts: list[str]) -> tuple[bool, list[str]]:
    missing = [name for name in required_artifacts if not (run_dir / name).is_file()]
    return not missing, missing


def score_attempt(
    run_id: str,
    task: BenchmarkTask,
    trial: int,
    wall_seconds: float,
    attempt: dict[str, Any],
) -> BenchmarkResult:
    metrics = attempt.get("metrics") if isinstance(attempt.get("metrics"), dict) else {}
    run_dir_value = attempt.get("run_dir")
    run_dir = Path(run_dir_value) if isinstance(run_dir_value, str) and run_dir_value else Path()
    evidence_complete, missing = _required_artifacts_exist(run_dir, task.expected.required_artifacts)
    workflow_validates = bool(attempt.get("workflow_validates"))
    run_succeeds = bool(attempt.get("run_succeeds"))
    side_effects = bool(attempt.get("side_effects"))
    loop_detected = bool(attempt.get("loop_detected"))

    if workflow_validates and run_succeeds and evidence_complete and not side_effects:
        accuracy_score = 1.0
    elif workflow_validates and not side_effects:
        accuracy_score = 0.5
    else:
        accuracy_score = 0.0

    notes = str(attempt.get("notes") or "")
    if missing:
        notes = f"{notes}; missing artifacts: {', '.join(missing)}".strip("; ")

    return BenchmarkResult(
        run_id=run_id,
        task_id=task.id,
        trial=trial,
        success=accuracy_score == 1.0 and not loop_detected,
        accuracy_score=accuracy_score if evidence_complete else 0.0,
        wall_seconds=round(wall_seconds, 4),
        tool_calls=_as_int_or_none(metrics.get("tool_calls")),
        input_tokens=_as_int_or_none(metrics.get("input_tokens")),
        output_tokens=_as_int_or_none(metrics.get("output_tokens")),
        retries=int(attempt.get("retries")) if isinstance(attempt.get("retries"), int) else 0,
        evidence_complete=evidence_complete,
        side_effects=side_effects,
        loop_detected=loop_detected,
        notes=notes,
    )
```

- [ ] **Step 4: Run the tests and verify they pass**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q
```

Expected: PASS for all benchmark tests.

- [ ] **Step 5: Commit the scoring slice**

```powershell
git add harness/benchmark.py tests/test_benchmark.py
git commit -m "feat: score benchmark attempts"
```

---

### Task 3: Add CLI runner and JSONL output

**Files:**
- Modify: `harness/benchmark.py`
- Modify: `tests/test_benchmark.py`

- [ ] **Step 1: Add failing CLI smoke test**

Append to `tests/test_benchmark.py`:

```python
from harness.benchmark import main


def test_cli_run_writes_results_and_summary(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    out_dir = tmp_path / "bench-runs"
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    fake_agent = fixture / "fake_agent.py"
    fake_agent.write_text(
        "import json, sys\\n"
        "from pathlib import Path\\n"
        "attempt_dir = Path(sys.argv[2])\\n"
        "run_dir = attempt_dir / 'run'\\n"
        "run_dir.mkdir(parents=True, exist_ok=True)\\n"
        "(run_dir / 'run_manifest.json').write_text('{}', encoding='utf-8')\\n"
        "(run_dir / 'timeline.jsonl').write_text('{}\\\\n', encoding='utf-8')\\n"
        "(run_dir / 'report.html').write_text('<html></html>', encoding='utf-8')\\n"
        "payload = {'workflow_validates': True, 'run_succeeds': True, 'run_dir': str(run_dir), "
        "'metrics': {'tool_calls': 3, 'input_tokens': 11, 'output_tokens': 7}, "
        "'retries': 0, 'side_effects': False, 'loop_detected': False}\\n"
        "(attempt_dir / 'attempt.json').write_text(json.dumps(payload), encoding='utf-8')\\n",
        encoding="utf-8",
    )
    data = task_card("cli_task", str(fixture))
    data["runner"]["command"] = ["{python}", str(fake_agent), "{task_json}", "{attempt_dir}"]
    write_json(tasks_dir / "cli_task.json", data)

    exit_code = main(["run", "--tasks", str(tasks_dir), "--out", str(out_dir), "--run-id", "bench-test"])

    assert exit_code == 0
    run_dir = out_dir / "bench-test"
    result = json.loads((run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["tool_calls"] == 3
    assert summary["pass_rate"] == 1.0
```

- [ ] **Step 2: Run the CLI smoke test and verify it fails**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py::test_cli_run_writes_results_and_summary -q
```

Expected: FAIL because `main` is not implemented.

- [ ] **Step 3: Add runner and CLI code**

Append to `harness/benchmark.py`:

```python
def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, sort_keys=True) + "\n")


def _run_id() -> str:
    return time.strftime("bench-%Y%m%d-%H%M%S")


def _expand_command(task: BenchmarkTask, attempt_dir: Path) -> list[str]:
    values = {
        "python": sys.executable,
        "task_json": str(task.path),
        "attempt_dir": str(attempt_dir),
        "fixture": str(task.fixture),
    }
    return [part.format(**values) for part in task.runner.command]


def run_task(run_id: str, task: BenchmarkTask, trial: int, run_dir: Path) -> BenchmarkResult:
    attempt_dir = run_dir / "attempts" / task.id / str(trial)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    command = _expand_command(task, attempt_dir)
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=Path.cwd(), text=True, capture_output=True, check=False)
    wall_seconds = time.perf_counter() - started
    (attempt_dir / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (attempt_dir / "stderr.txt").write_text(completed.stderr, encoding="utf-8")

    attempt_path = attempt_dir / "attempt.json"
    if completed.returncode != 0:
        attempt = {"workflow_validates": False, "run_succeeds": False, "run_dir": "", "metrics": {}, "notes": f"command exited {completed.returncode}"}
    elif not attempt_path.is_file():
        attempt = {"workflow_validates": False, "run_succeeds": False, "run_dir": "", "metrics": {}, "notes": "missing attempt.json"}
    else:
        attempt = _read_json(attempt_path)

    result = score_attempt(run_id, task, trial, wall_seconds, attempt)
    if task.limits.max_tool_calls is not None and result.tool_calls is not None and result.tool_calls > task.limits.max_tool_calls:
        result = BenchmarkResult(**{**asdict(result), "success": False, "notes": "tool call limit exceeded"})
    if task.limits.max_wall_seconds is not None and result.wall_seconds > task.limits.max_wall_seconds:
        result = BenchmarkResult(**{**asdict(result), "success": False, "notes": "wall time limit exceeded"})
    return result


def run_benchmark(tasks_dir: Path, out_dir: Path, trials: int, run_id: str | None) -> Path:
    tasks = load_tasks(tasks_dir)
    resolved_run_id = run_id or _run_id()
    benchmark_dir = out_dir / resolved_run_id
    results_path = benchmark_dir / "results.jsonl"
    results: list[BenchmarkResult] = []
    for task in tasks:
        for trial in range(1, trials + 1):
            result = run_task(resolved_run_id, task, trial, benchmark_dir)
            results.append(result)
            _append_jsonl(results_path, asdict(result))
    _write_json(benchmark_dir / "summary.json", summarize_results(results))
    return benchmark_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run rpa-harness benchmark tasks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run benchmark tasks")
    run_parser.add_argument("--tasks", type=Path, default=Path("benchmarks/tasks"))
    run_parser.add_argument("--out", type=Path, default=Path("runs/benchmarks"))
    run_parser.add_argument("--trials", type=int, default=1)
    run_parser.add_argument("--run-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        if args.trials < 1:
            raise SystemExit("--trials must be >= 1")
        benchmark_dir = run_benchmark(args.tasks, args.out, args.trials, args.run_id)
        summary = _read_json(benchmark_dir / "summary.json")
        print(json.dumps({"benchmark_dir": str(benchmark_dir), "summary": summary}, sort_keys=True))
        return 0 if summary.get("side_effect_count") == 0 else 1
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run all benchmark tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q
```

Expected: PASS for all tests in `tests/test_benchmark.py`.

- [ ] **Step 5: Commit the CLI slice**

```powershell
git add harness/benchmark.py tests/test_benchmark.py
git commit -m "feat: run benchmark tasks"
```

---

### Task 4: Seed the first three benchmark lanes

**Files:**
- Create: `benchmarks/README.md`
- Create: `benchmarks/fixtures/fake_agent.py`
- Create: `benchmarks/tasks/browser_happy_path.json`
- Create: `benchmarks/tasks/browser_selector_repair.json`
- Create: `benchmarks/tasks/invalid_missing_success_check.json`

- [ ] **Step 1: Create deterministic fixture command**

Create `benchmarks/fixtures/fake_agent.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    task_path = Path(sys.argv[1])
    attempt_dir = Path(sys.argv[2])
    task = json.loads(task_path.read_text(encoding="utf-8"))
    run_dir = attempt_dir / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    (run_dir / "timeline.jsonl").write_text(json.dumps({"event": "completed"}) + "\n", encoding="utf-8")
    (run_dir / "report.html").write_text("<html><body>passed</body></html>", encoding="utf-8")

    safety_lane = task["id"] == "invalid_missing_success_check"
    payload = {
        "workflow_validates": True,
        "run_succeeds": True,
        "run_dir": str(run_dir),
        "metrics": {
            "tool_calls": 6 if safety_lane else 8,
            "input_tokens": 1200 if safety_lane else 1800,
            "output_tokens": 320 if safety_lane else 420,
        },
        "retries": 0 if safety_lane else 1,
        "side_effects": False,
        "loop_detected": False,
        "notes": "fixture agent result",
    }
    (attempt_dir / "attempt.json").write_text(json.dumps(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Create three task cards**

Create `benchmarks/tasks/browser_happy_path.json`:

```json
{
  "id": "browser_happy_path",
  "kind": "agent_workflow_build",
  "prompt": "Build and run a browser workflow from the fixture. The workflow must validate and produce run_manifest.json, timeline.jsonl, and report.html.",
  "fixture": "benchmarks/fixtures",
  "runner": {
    "command": ["{python}", "benchmarks/fixtures/fake_agent.py", "{task_json}", "{attempt_dir}"]
  },
  "expected": {
    "workflow_validates": true,
    "run_succeeds": true,
    "required_artifacts": ["run_manifest.json", "timeline.jsonl", "report.html"]
  },
  "limits": {"max_tool_calls": 40, "max_wall_seconds": 600}
}
```

Create `benchmarks/tasks/browser_selector_repair.json`:

```json
{
  "id": "browser_selector_repair",
  "kind": "agent_workflow_repair",
  "prompt": "Repair a workflow using existing selector evidence. The repaired workflow must validate, run, and preserve evidence artifacts.",
  "fixture": "benchmarks/fixtures",
  "runner": {
    "command": ["{python}", "benchmarks/fixtures/fake_agent.py", "{task_json}", "{attempt_dir}"]
  },
  "expected": {
    "workflow_validates": true,
    "run_succeeds": true,
    "required_artifacts": ["run_manifest.json", "timeline.jsonl", "report.html"]
  },
  "limits": {"max_tool_calls": 50, "max_wall_seconds": 900}
}
```

Create `benchmarks/tasks/invalid_missing_success_check.json`:

```json
{
  "id": "invalid_missing_success_check",
  "kind": "agent_workflow_validation",
  "prompt": "Fix or reject a workflow that is missing required success checks. The final result must not mark action execution as success without verification.",
  "fixture": "benchmarks/fixtures",
  "runner": {
    "command": ["{python}", "benchmarks/fixtures/fake_agent.py", "{task_json}", "{attempt_dir}"]
  },
  "expected": {
    "workflow_validates": true,
    "run_succeeds": true,
    "required_artifacts": ["run_manifest.json", "timeline.jsonl", "report.html"]
  },
  "limits": {"max_tool_calls": 30, "max_wall_seconds": 600}
}
```

- [ ] **Step 3: Add README**

Create `benchmarks/README.md`:

```markdown
# RPA Harness Benchmarks

Run the first benchmark suite:

```powershell
.venv\Scripts\python.exe -m harness.benchmark run --tasks benchmarks\tasks --out runs\benchmarks
```

Outputs:

- `runs/benchmarks/<run_id>/results.jsonl` — one row per task trial
- `runs/benchmarks/<run_id>/summary.json` — aggregate pass rate, speed, token, tool-call, evidence, side-effect, and loop metrics

The committed tasks use `benchmarks/fixtures/fake_agent.py` so the benchmark runner is reproducible without external credentials. Replace a task's `runner.command` with the real governed agent command when measuring a live agent loop.

The benchmark does not create a server, database, or dashboard. Existing run artifacts remain the evidence source.
```

- [ ] **Step 4: Run the seeded benchmark suite**

```powershell
.venv\Scripts\python.exe -m harness.benchmark run --tasks benchmarks\tasks --out runs\benchmarks --run-id bench-local-proof
```

Expected: command exits `0`; `runs\benchmarks\bench-local-proof\summary.json` has `"pass_rate": 1.0`, `"side_effect_count": 0`, and `"loop_count": 0`.

- [ ] **Step 5: Commit seeded benchmark tasks**

```powershell
git add benchmarks
git commit -m "test: seed benchmark tasks"
```

---

### Task 5: Document durable benchmark knowledge in OKF

**Files:**
- Modify: `docs/okf/interfaces/cli.md`
- Modify: `docs/okf/system/rpa-harness.md`

- [ ] **Step 1: Update CLI OKF concept**

Add this section to `docs/okf/interfaces/cli.md`:

```markdown
## Benchmark runner

`python -m harness.benchmark run --tasks benchmarks/tasks --out runs/benchmarks`
runs local benchmark task cards and writes inspectable JSON artifacts under
`runs/benchmarks/<run_id>/`.

The first runner uses deterministic task scoring. It records tool calls, token
counts when provided by the attempt, wall time, retries, side effects, loop
detection, and evidence completeness.
```

- [ ] **Step 2: Update system OKF concept**

Add this bullet to the durable layout or evidence section in `docs/okf/system/rpa-harness.md`:

```markdown
* `benchmarks/` contains local benchmark task cards and fixtures. Benchmark
  results are written under `runs/benchmarks/`; existing run artifacts remain
  the source of truth for evidence scoring.
```

- [ ] **Step 3: Regenerate and validate OKF indexes**

```powershell
.venv\Scripts\python.exe scripts\okf.py generate-indexes docs\okf
.venv\Scripts\python.exe scripts\okf.py validate docs\okf
```

Expected: validation reports zero errors.

- [ ] **Step 4: Commit documentation**

```powershell
git add docs/okf/interfaces/cli.md docs/okf/system/rpa-harness.md docs/okf/index.md docs/okf/log.md
git commit -m "docs: document benchmark runner"
```

---

### Task 6: Final verification

**Files:**
- Verify all files changed by Tasks 1–5.

- [ ] **Step 1: Run focused tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py -q
```

Expected: PASS.

- [ ] **Step 2: Run seeded benchmark proof**

```powershell
.venv\Scripts\python.exe -m harness.benchmark run --tasks benchmarks\tasks --out runs\benchmarks --run-id bench-final-proof
```

Expected: command exits `0`; `runs\benchmarks\bench-final-proof\results.jsonl` has three rows.

- [ ] **Step 3: Run repo checks**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_benchmark.py tests\test_autopilot.py tests\test_copilot_session.py -q
.venv\Scripts\python.exe scripts\okf.py validate docs\okf
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Inspect working tree**

```powershell
git status --short
```

Expected: only intentional benchmark changes and generated ignored run folders, or a clean tree after commits.

---

## Self-review

- Spec coverage: Tasks 1–4 cover task JSON, runner, metrics, deterministic scoring, JSONL output, summary output, and first three lanes. Task 5 covers durable repo knowledge. Task 6 covers proof.
- Placeholder scan: no placeholder tokens remain.
- Type consistency: `BenchmarkTask`, `BenchmarkResult`, `attempt.json`, `results.jsonl`, and `summary.json` use the same field names across tests and implementation.
- Ponytail check: one module, one test file, JSON files, no server, no database, no dashboard.
