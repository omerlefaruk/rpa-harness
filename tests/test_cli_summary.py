"""CLI summary failure gate tests."""

from main import has_run_failures


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
