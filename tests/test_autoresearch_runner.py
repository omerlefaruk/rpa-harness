"""Tests for the deterministic autoresearch runner."""

from __future__ import annotations

import json
from pathlib import Path

from tools.autoresearch_runner import (
    AutoresearchConfig,
    CommandResult,
    append_jsonl,
    build_codex_prompt,
    build_run_entry,
    decide_status,
    heartbeat_secret_scan,
    parse_metric_lines,
    read_jsonl,
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


def test_secret_scan_fails_on_sensitive_session_content(tmp_path):
    config = _config(tmp_path)
    config.session_dir.mkdir()
    config.markdown_path.write_text("password=abc123", encoding="utf-8")

    check = heartbeat_secret_scan(config)

    assert check.status == "fail"
    assert "autoresearch.md" in check.detail


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
    assert "Recent runs" in prompt
    assert "Improve memory scoring" in prompt
    json.loads(prompt.split("Recent runs:\n", 1)[1].split("\n\nIdeas:", 1)[0])
