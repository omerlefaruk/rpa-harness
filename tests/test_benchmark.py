import json
from pathlib import Path

import pytest

from harness.benchmark import BenchmarkResult, load_tasks, score_attempt, summarize_results


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
            "command": [
                "{python}",
                "benchmarks/fixtures/fake_agent.py",
                "{task_json}",
                "{attempt_dir}",
            ]
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
    assert tasks[0].expected.required_artifacts == [
        "run_manifest.json",
        "timeline.jsonl",
        "report.html",
    ]


def test_load_tasks_rejects_missing_required_fields(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    write_json(tasks_dir / "bad.json", {"id": "bad"})

    with pytest.raises(ValueError, match="bad.json"):
        load_tasks(tasks_dir)


def test_summarize_results_aggregates_core_metrics() -> None:
    results = [
        BenchmarkResult(
            "bench-1",
            "a",
            1,
            True,
            1.0,
            2.0,
            10,
            100,
            20,
            0,
            True,
            False,
            False,
            "",
        ),
        BenchmarkResult(
            "bench-1",
            "b",
            1,
            False,
            0.0,
            4.0,
            None,
            None,
            None,
            2,
            False,
            True,
            True,
            "failed",
        ),
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
    attempt = {
        "workflow_validates": True,
        "run_succeeds": False,
        "run_dir": str(run_dir),
        "metrics": {},
    }

    result = score_attempt("bench-1", task, 1, 2.0, attempt)

    assert result.success is False
    assert result.accuracy_score == 0.5
    assert result.evidence_complete is True
    assert result.tool_calls is None


def test_score_attempt_fails_when_required_artifact_is_missing(tmp_path: Path) -> None:
    task = make_task(tmp_path, ["run_manifest.json", "report.html"])
    run_dir = tmp_path / "run"
    write_run_artifacts(run_dir, ["run_manifest.json"])
    attempt = {
        "workflow_validates": True,
        "run_succeeds": True,
        "run_dir": str(run_dir),
        "metrics": {},
    }

    result = score_attempt("bench-1", task, 1, 2.0, attempt)

    assert result.success is False
    assert result.accuracy_score == 0.0
    assert result.evidence_complete is False
    assert "missing artifacts" in result.notes
