"""Tests for the deterministic autoresearch runner."""

from __future__ import annotations

import json
from pathlib import Path

from tools import autoresearch_runner as runner
from tools.autoresearch_runner import (
    CHANGE_MANIFEST_ENV,
    AutoresearchConfig,
    CommandResult,
    append_jsonl,
    best_entry,
    best_kept_metric,
    build_codex_prompt,
    build_run_entry,
    compute_confidence,
    dashboard_data,
    decide_status,
    heartbeat_secret_scan,
    load_change_manifest,
    parse_metric_lines,
    read_jsonl,
    render_dashboard_html,
    run_command,
    run_once,
    save_to_memory,
    write_dashboard,
)


def _config(tmp_path: Path) -> AutoresearchConfig:
    return AutoresearchConfig(
        workdir=tmp_path,
        session_dir=tmp_path / ".autoresearch",
        objective="Improve tests",
        metric_name="score",
        direction="higher",
        memory_required=False,
    )


def _write_session_files(config: AutoresearchConfig) -> None:
    config.session_dir.mkdir(parents=True, exist_ok=True)
    config.markdown_path.write_text("# Autoresearch\n", encoding="utf-8")
    (config.session_dir / "autoresearch.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")


def test_parse_metric_lines_accepts_finite_metrics_and_rejects_polluting_names():
    output = """
noise
METRIC score=0.91
METRIC default_cli_seconds=12.5
METRIC __proto__=1
METRIC bad=nan
"""

    assert parse_metric_lines(output) == {
        "score": 0.91,
        "default_cli_seconds": 12.5,
    }


def test_decide_status_keeps_baseline_and_discards_non_improvement():
    assert decide_status(1.0, True, True, [], "higher") == "keep"
    previous = [{"type": "run", "status": "keep", "metric": 1.0}]

    assert decide_status(0.9, True, True, previous, "higher") == "discard"
    assert decide_status(1.1, True, True, previous, "higher") == "keep"
    assert decide_status(1.2, True, False, previous, "higher") == "checks_failed"
    assert decide_status(None, False, False, previous, "higher") == "crash"


def test_decide_status_uses_matching_metric_history_only():
    previous = [
        {"type": "run", "status": "keep", "metric": 99, "metric_name": "old_metric"},
    ]

    assert decide_status(1, True, True, previous, "higher", metric_name="new_metric") == "keep"
    assert decide_status(1, True, True, previous, "higher", metric_name="old_metric") == "discard"


def test_append_jsonl_redacts_sensitive_content(tmp_path):
    path = tmp_path / ".autoresearch" / "autoresearch.jsonl"

    append_jsonl(
        path,
        {
            "type": "run",
            "status": "keep",
            "metric": 1,
            "headers": {"Authorization": "Bearer secret-token"},
            "tail_output": "password=super-secret",
        },
    )

    text = path.read_text(encoding="utf-8")
    assert "secret-token" not in text
    assert "super-secret" not in text
    entries = read_jsonl(path)
    assert entries[0]["headers"]["Authorization"] == "[REDACTED]"
    assert entries[0]["tail_output"] == "password=[REDACTED]"


def test_read_jsonl_ignores_bad_lines_and_non_run_entries(tmp_path):
    path = tmp_path / ".autoresearch" / "autoresearch.jsonl"
    path.parent.mkdir()
    path.write_text(
        "\n".join(
            [
                "not json",
                json.dumps({"type": "note", "status": "ignore"}),
                json.dumps({"type": "run", "run": 1, "status": "keep", "metric": 1}),
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert read_jsonl(path) == [{"type": "run", "run": 1, "status": "keep", "metric": 1}]


def test_build_run_entry_marks_checks_failed_when_benchmark_passes_but_checks_fail(tmp_path):
    config = _config(tmp_path)
    benchmark = CommandResult(
        command="benchmark",
        exit_code=0,
        duration_seconds=1.2,
        stdout="METRIC score=2",
        stderr="",
    )
    checks = CommandResult(
        command="checks",
        exit_code=1,
        duration_seconds=0.2,
        stdout="",
        stderr="failure",
    )

    entry = build_run_entry(
        config=config,
        previous=[],
        heartbeat=[],
        benchmark=benchmark,
        checks_result=checks,
        metrics={"score": 2},
    )

    assert entry["status"] == "checks_failed"
    assert entry["metric"] == 2
    assert entry["lesson"] == "Benchmark produced a metric, but correctness checks failed."


def test_build_run_entry_records_change_manifest_and_aggregate_attribution(tmp_path):
    config = _config(tmp_path)
    benchmark = CommandResult(
        command="benchmark",
        exit_code=0,
        duration_seconds=1.0,
        stdout="METRIC score=2",
        stderr="",
    )
    checks = CommandResult(command="checks", exit_code=0, duration_seconds=0.2, stdout="", stderr="")

    entry = build_run_entry(
        config=config,
        previous=[{"type": "run", "status": "keep", "metric": 1, "metric_name": "score"}],
        heartbeat=[],
        benchmark=benchmark,
        checks_result=checks,
        metrics={"score": 2},
        change_manifest={
            "source": "test",
            "hypothesis": "Improve score",
            "failure_evidence": ["previous score was low"],
            "root_cause": "missing evidence contract",
            "targeted_fix": "add manifest tracking",
            "component_type": "tooling",
            "changed_files": ["tools/autoresearch_runner.py"],
            "predicted_fixes": ["score improves"],
            "predicted_regressions": ["checks fail"],
            "rollback_hint": "discard run",
        },
    )

    assert entry["status"] == "keep"
    assert entry["change_manifest"]["component_type"] == "tooling"
    assert entry["change_manifest"]["failure_evidence"] == ["previous score was low"]
    attribution = entry["change_attribution"]
    assert attribution["metric_delta"] == 1
    assert attribution["prediction_summary"]["fix_prediction_supported"] is True
    assert attribution["prediction_summary"]["regression_prediction_supported"] is False


def test_build_run_entry_adds_per_target_attribution_when_task_metrics_exist(tmp_path):
    config = _config(tmp_path)
    benchmark = CommandResult(
        command="benchmark",
        exit_code=0,
        duration_seconds=1.0,
        stdout="METRIC score=2\nMETRIC task.login=1\nMETRIC task.checkout=0\nMETRIC task.report=0",
        stderr="",
    )
    checks = CommandResult(command="checks", exit_code=0, duration_seconds=0.2, stdout="", stderr="")

    entry = build_run_entry(
        config=config,
        previous=[
            {
                "type": "run",
                "status": "keep",
                "metric": 1,
                "metric_name": "score",
                "metrics": {"score": 1, "task.login": 0, "task.checkout": 1, "task.report": 0},
            }
        ],
        heartbeat=[],
        benchmark=benchmark,
        checks_result=checks,
        metrics={"score": 2, "task.login": 1, "task.checkout": 0, "task.report": 0},
        change_manifest={
            "predicted_fixes": ["login should pass", "unmatched task"],
            "predicted_regressions": ["checkout may regress"],
        },
    )

    attribution = entry["change_attribution"]
    assert attribution["mode"] == "per_target_and_aggregate"
    per_target = attribution["per_target"]
    assert per_target["observed_improved"] == ["login"]
    assert per_target["observed_regressed"] == ["checkout"]
    assert per_target["observed_unchanged"] == ["report"]
    assert per_target["fix_true_positives"] == ["login"]
    assert per_target["regression_true_positives"] == ["checkout"]
    assert per_target["fix_precision"] == 0.5
    assert per_target["fix_recall"] == 1.0
    assert per_target["regression_precision"] == 1.0
    assert per_target["regression_recall"] == 1.0
    assert attribution["prediction_summary"]["regression_prediction_supported"] is True


def test_per_target_attribution_uses_previous_kept_metrics_and_higher_is_better(tmp_path):
    config = _config(tmp_path)
    config.direction = "lower"
    benchmark = CommandResult(
        command="benchmark",
        exit_code=0,
        duration_seconds=1.0,
        stdout="METRIC score=0.5\nMETRIC task.login=1",
        stderr="",
    )
    checks = CommandResult(command="checks", exit_code=0, duration_seconds=0.2, stdout="", stderr="")

    entry = build_run_entry(
        config=config,
        previous=[
            {
                "type": "run",
                "status": "keep",
                "metric": 1,
                "metric_name": "score",
                "metrics": {"score": 1, "task.login": 0},
            },
            {
                "type": "run",
                "status": "discard",
                "metric": 2,
                "metric_name": "score",
                "metrics": {"score": 2, "task.login": 1},
            },
        ],
        heartbeat=[],
        benchmark=benchmark,
        checks_result=checks,
        metrics={"score": 0.5, "task.login": 1},
        change_manifest={"predicted_fixes": ["login"]},
    )

    per_target = entry["change_attribution"]["per_target"]
    assert per_target["observed_improved"] == ["login"]
    assert per_target["observed_regressed"] == []


def test_load_change_manifest_handles_missing_malformed_and_valid_env(monkeypatch):
    monkeypatch.delenv(CHANGE_MANIFEST_ENV, raising=False)
    assert load_change_manifest() is None

    monkeypatch.setenv(CHANGE_MANIFEST_ENV, "password=secret")
    malformed = load_change_manifest()
    assert malformed["manifest_error"] == "invalid_json"
    assert "secret" not in malformed["raw_preview"]

    monkeypatch.setenv(CHANGE_MANIFEST_ENV, json.dumps(["not", "object"]))
    assert load_change_manifest()["manifest_error"] == "not_an_object"

    monkeypatch.setenv(CHANGE_MANIFEST_ENV, json.dumps({"hypothesis": "improve"}))
    assert load_change_manifest()["hypothesis"] == "improve"


def test_secret_scan_fails_on_sensitive_session_content(tmp_path):
    config = _config(tmp_path)
    config.session_dir.mkdir()
    config.markdown_path.write_text("password=abc123", encoding="utf-8")

    check = heartbeat_secret_scan(config)

    assert check.status == "fail"
    assert "autoresearch.md" in check.detail


def test_best_entry_respects_direction_and_kept_status_only():
    entries = [
        {"status": "keep", "metric": 10},
        {"status": "discard", "metric": 50},
        {"status": "keep", "metric": 5},
    ]

    assert best_entry(entries, "higher") == entries[0]
    assert best_entry(entries, "lower") == entries[2]


def test_best_metric_helpers_can_scope_by_metric_name():
    entries = [
        {"status": "keep", "metric": 10, "metric_name": "speed"},
        {"status": "keep", "metric": 5, "metric_name": "quality"},
        {"status": "discard", "metric": 50, "metric_name": "quality"},
    ]

    assert best_kept_metric(entries, "higher", metric_name="quality") == 5
    assert best_entry(entries, "higher", metric_name="quality") == entries[1]
    assert best_kept_metric(entries, "higher", metric_name="missing") is None


def test_compute_confidence_uses_median_absolute_deviation():
    entries = [
        {"status": "keep", "metric": 10},
        {"status": "keep", "metric": 11},
        {"status": "discard", "metric": 9},
        {"status": "keep", "metric": 14},
    ]

    assert compute_confidence(entries, "higher") == 4.0


def test_compute_confidence_can_scope_by_metric_name():
    entries = [
        {"status": "keep", "metric": 1, "metric_name": "old"},
        {"status": "keep", "metric": 10, "metric_name": "new"},
        {"status": "keep", "metric": 12, "metric_name": "new"},
        {"status": "keep", "metric": 18, "metric_name": "new"},
    ]

    assert compute_confidence(entries, "higher", metric_name="new") == 4.0
    assert compute_confidence(entries, "higher", metric_name="old") is None


def test_run_once_records_required_memory_save_failure(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _write_session_files(config)
    config.benchmark_command = "bench"
    config.checks_command = "checks"
    config.memory_required = True

    def _fake_run_command(command, *_args, **_kwargs):
        if command == "bench":
            return CommandResult("bench", 0, 0.1, "METRIC score=1\n", "")
        return CommandResult("checks", 0, 0.1, "", "")

    def _fail_memory(*_args, **_kwargs):
        raise TimeoutError("memory down")

    monkeypatch.setattr(runner, "run_heartbeat", lambda _config: [])
    monkeypatch.setattr(runner, "run_command", _fake_run_command)
    monkeypatch.setattr(runner, "save_to_memory", _fail_memory)

    assert run_once(config) == 1
    entry = read_jsonl(config.jsonl_path)[0]
    assert entry["status"] == "checks_failed"
    assert entry["memory_save"]["status"] == "failed"
    assert entry["lesson"] == "Required RPA Memory save failed."


def test_save_to_memory_reports_optional_unavailable_service(tmp_path):
    config = _config(tmp_path)
    config.memory_url = "http://127.0.0.1:1"

    result = save_to_memory(
        config,
        {"run": 1, "status": "keep", "metric_name": "score", "change_manifest": {}},
    )

    assert result["status"] == "unavailable"
    assert result["detail"]


def test_dashboard_data_summarizes_runs_statuses_metrics_and_latest(tmp_path):
    config = _config(tmp_path)
    _write_session_files(config)
    append_jsonl(
        config.jsonl_path,
        {
            "type": "run",
            "run": 1,
            "status": "keep",
            "metric": 1,
            "metric_name": "score",
            "metrics": {"score": 1, "latency": 10},
            "confidence": None,
            "lesson": "baseline",
            "benchmark": {"command": "bench"},
            "checks": {"exit_code": 0},
        },
    )
    append_jsonl(
        config.jsonl_path,
        {
            "type": "run",
            "run": 2,
            "status": "discard",
            "metric": 0.5,
            "metric_name": "score",
            "metrics": {"score": 0.5},
            "confidence": None,
            "lesson": "not better",
            "benchmark": {"command": "bench"},
            "checks": {"exit_code": 0},
        },
    )
    append_jsonl(
        config.jsonl_path,
        {
            "type": "run",
            "run": 3,
            "status": "keep",
            "metric": 2,
            "metric_name": "score",
            "metrics": {"score": 2},
            "confidence": 2.5,
            "lesson": "accepted",
            "benchmark": {"command": "bench"},
            "checks": {"exit_code": 0},
        },
    )

    data = dashboard_data(config)

    assert data["run_count"] == 3
    assert data["statuses"]["keep"] == 2
    assert data["statuses"]["discard"] == 1
    assert data["best"]["run"] == 3
    assert data["latest"]["run"] == 3
    assert data["metric_names"] == ["latency", "score"]
    assert [item["run"] for item in data["implementations"]] == [3, 2, 1]
    assert "change_attribution" in data["series"][0]
    assert "component_type" in data["implementations"][0]


def test_dashboard_data_handles_empty_log(tmp_path):
    config = _config(tmp_path)
    _write_session_files(config)

    data = dashboard_data(config)

    assert data["run_count"] == 0
    assert data["best"] is None
    assert data["latest"] is None
    assert data["statuses"] == {"keep": 0, "discard": 0, "crash": 0, "checks_failed": 0}


def test_render_dashboard_html_contains_live_refresh_controls(tmp_path):
    config = _config(tmp_path)
    data = {
        "objective": "Improve tests",
        "metric_name": "score",
        "direction": "higher",
        "run_count": 1,
        "best": {"metric": 1},
        "latest": {"status": "keep", "confidence": None},
        "metric_names": ["score"],
        "heartbeat": [],
        "series": [],
        "generated_at": "now",
        "session_dir": str(config.session_dir),
    }

    html = render_dashboard_html(config, data, live=True)

    assert "Autoresearch Control" in html
    assert "Attribution" in html
    assert "attributionSummary" in html
    assert "const live = true;" in html
    assert 'fetch("/data.json"' in html


def test_render_dashboard_html_snapshot_disables_live_refresh(tmp_path):
    config = _config(tmp_path)

    html = render_dashboard_html(config, {"objective": "snapshot"}, live=False)

    assert "SNAPSHOT" in html
    assert "const live = false;" in html


def test_render_dashboard_html_escapes_log_derived_html(tmp_path):
    config = _config(tmp_path)
    data = {
        "objective": "x</script><script>alert(1)</script>",
        "metric_name": "score",
        "direction": "higher",
        "run_count": 1,
        "best": None,
        "latest": {"status": "keep", "confidence": None},
        "metric_names": ['<img src=x onerror="alert(1)">'],
        "heartbeat": [{"name": "<b>memory</b>", "status": "warn", "detail": "<i>down</i>"}],
        "series": [
            {
                "run": 1,
                "status": "keep",
                "metric": 1,
                "lesson": '<img src=x onerror="alert(1)">',
                "timestamp": "<time>",
            }
        ],
        "generated_at": "now",
        "session_dir": str(config.session_dir),
    }

    rendered = render_dashboard_html(config, data, live=True)

    assert "x</script><script>" not in rendered
    assert "<\\/script><script>" in rendered
    assert "escapeHtml(run.lesson" in rendered
    assert "escapeHtml(item.detail" in rendered


def test_write_dashboard_writes_snapshot_file(tmp_path):
    config = _config(tmp_path)
    _write_session_files(config)

    output = write_dashboard(config, str(tmp_path / "dashboard.html"))

    assert output.exists()
    assert "SNAPSHOT" in output.read_text(encoding="utf-8")


def test_run_command_reports_timeouts(tmp_path):
    result = run_command('python3 -c "import time; time.sleep(2)"', tmp_path, 0)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.passed is False


def test_run_command_passes_extra_environment(tmp_path):
    result = run_command(
        'python -c "import os; print(os.getenv(\'AHE_TEST_ENV\'))"',
        tmp_path,
        5,
        extra_env={"AHE_TEST_ENV": "visible"},
    )

    assert result.passed
    assert "visible" in result.stdout


def test_build_codex_prompt_includes_allowed_scope_and_recent_runs(tmp_path):
    config = _config(tmp_path)
    config.session_dir.mkdir()
    config.ideas_path.write_text("- [ ] Improve memory scoring\n", encoding="utf-8")
    append_jsonl(
        config.jsonl_path,
        {
            "type": "run",
            "run": 1,
            "status": "keep",
            "metric": 1,
            "metric_name": "score",
        },
    )

    prompt = build_codex_prompt(config)

    assert "Allowed paths" in prompt
    assert "tools/" in prompt
    assert "make the change falsifiable" in prompt
    assert "Recent runs" in prompt
    assert "Improve memory scoring" in prompt
    json.loads(prompt.split("Recent runs:\n", 1)[1].split("\n\nIdeas:", 1)[0])
