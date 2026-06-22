"""CLI summary failure gate tests."""

import json

from main import has_run_failures
from harness.reporting.run_artifacts import print_runs_list


def test_has_run_failures_counts_failed_workflows_without_record_failures():
    summary = {
        "tests": {"failed": 0},
        "workflows": {"failed": 1, "failed_records": 0},
    }

    assert has_run_failures(summary)


def test_has_run_failures_counts_failed_workflow_records():
    summary = {
        "tests": {"failed": 0},
        "workflows": {"failed": 0, "failed_records": 1},
    }

    assert has_run_failures(summary)


def test_has_run_failures_accepts_clean_test_only_runs():
    summary = {"tests": {"failed": 0}, "workflows": None}

    assert not has_run_failures(summary)


def test_print_runs_list_uses_manifest_reader(tmp_path, capsys):
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "workflow": "wf",
                "status": "passed",
                "summary": {"passed_steps": 2, "total_steps": 3},
            }
        ),
        encoding="utf-8",
    )

    print_runs_list(str(tmp_path / "runs"))

    output = capsys.readouterr().out
    assert "run-1  passed  wf" in output
    assert "steps 2/3" in output
    assert "report.html" in output
