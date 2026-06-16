import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness.observability import ObservabilityDB, index_runs
from harness.reporting.dashboard import create_dashboard
from harness.rpa.schema import (
    generate_workflow_graph,
    load_workflow_yaml_compat,
    migrate_legacy_workflow,
    validate_workflow_schema,
)


CANARY = "sk-test-canary-12345"


def test_default_schema_validates_and_generates_graph(tmp_path):
    workflow = {
        "schema_version": 2,
        "name": "upload_invoices",
        "secrets": [{"name": "ACME_PASSWORD", "required": True}],
        "inputs": {"primary": {"type": "excel", "path": "invoices.xlsx"}},
        "targets": {"portal": {"type": "browser", "base_url": "https://example.test"}},
        "phases": [
            {
                "id": "login",
                "steps": [
                    {
                        "id": "open_login",
                        "target": "portal",
                        "action": {"type": "browser.goto", "url": "https://example.test/login"},
                        "success_checks": [{"type": "url_contains", "value": "/login"}],
                    }
                ],
            }
        ],
    }

    validation = validate_workflow_schema(workflow)
    graph = generate_workflow_graph(workflow)

    assert validation["errors"] == []
    assert graph["workflow"] == "upload_invoices"
    assert graph["summary"]["total_phases"] == 1
    assert graph["summary"]["steps_with_success_checks"] == 1


def test_default_schema_rejects_missing_success_check_and_unsafe_retry():
    workflow = {
        "schema_version": 2,
        "name": "bad",
        "targets": {"api": {"type": "api"}},
        "phases": [
            {
                "id": "main",
                "steps": [
                    {
                        "id": "write",
                        "target": "api",
                        "side_effect": "external_write",
                        "retryable": True,
                        "action": {"type": "api.post", "url": "https://example.test"},
                    }
                ],
            }
        ],
    }

    errors = validate_workflow_schema(workflow)["errors"]

    assert any("missing success_checks" in error for error in errors)
    assert any("retryable external_write requires idempotency_key" in error for error in errors)


def test_migrate_legacy_workflow_preserves_success_checks_and_redacts(tmp_path):
    source = tmp_path / "old.yaml"
    target = tmp_path / "new.yaml"
    report = tmp_path / "migration_report.md"
    source.write_text(
        """
id: old_flow
name: Old Flow
version: "1"
type: api
credentials:
  api_token: API_TOKEN
steps:
  - id: read
    action:
      type: api.get
      url: https://example.test
    success_check:
      - type: status_code
        value: 200
  - id: write
    phase: submit
    action:
      type: api.post
      url: https://example.test
      headers:
        Authorization: Bearer sk-test-canary-12345
    success_check:
      - type: status_code
        value: 201
""",
        encoding="utf-8",
    )

    result = migrate_legacy_workflow(source, target, report)
    migrated = load_workflow_yaml_compat(target)

    assert result["status"] == "written"
    assert migrated["id"] == "old_flow"
    assert [step["id"] for step in migrated["steps"]] == ["read", "write"]
    assert migrated["steps"][0]["success_check"][0]["type"] == "status_code"
    assert CANARY not in target.read_text(encoding="utf-8")
    assert CANARY not in report.read_text(encoding="utf-8")


def test_observability_indexes_runs_idempotently_and_redacts(tmp_path):
    run = tmp_path / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "workflow": "wf",
                "schema_version": 1,
                "status": "failed",
                "started_at": "2026-06-16T00:00:00Z",
                "finished_at": "2026-06-16T00:00:01Z",
                "run_directory": str(run),
                "report": "report.html",
                "timeline": "timeline.jsonl",
                "records": "records.jsonl",
                "preflight": "preflight.json",
                "redaction": {"status": "passed"},
            }
        ),
        encoding="utf-8",
    )
    (run / "timeline.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-06-16T00:00:00Z",
                "run_id": "run-1",
                "workflow": "wf",
                "event": "step.failed",
                "phase": "login",
                "step_id": "submit",
                "status": "failed",
                "failure_kind": "verification_failed",
                "message": f"token={CANARY}",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "records.jsonl").write_text(
        json.dumps({"run_id": "run-1", "workflow": "wf", "record_id": "A", "status": "failed"})
        + "\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "runs" / "observability.db"
    first = index_runs(tmp_path / "runs", db_path)
    second = index_runs(tmp_path / "runs", db_path)
    db = ObservabilityDB(db_path)

    assert first["indexed_runs"] == 1
    assert second["indexed_runs"] == 1
    assert db.list_runs()[0]["run_id"] == "run-1"
    assert db.get_failure_kinds_summary()[0]["failure_kind"] == "verification_failed"
    assert db.get_run_records("run-1")[0]["record_id"] == "A"
    assert CANARY.encode() not in db_path.read_bytes()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from timeline_events").fetchone()[0] == 1


def test_dashboard_api_artifact_and_live_polling_are_safe(tmp_path):
    run = tmp_path / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(
        json.dumps({"run_id": "run-1", "workflow": "wf", "status": "failed", "run_directory": str(run)}),
        encoding="utf-8",
    )
    (run / "timeline.jsonl").write_text(
        '{"event_id":1,"run_id":"run-1","event":"step.started","message":"ok"}\n'
        '{"event_id":2,"run_id":"run-1","event":"step.failed","message":"token=sk-test-canary-12345"}\n',
        encoding="utf-8",
    )
    (run / "report.html").write_text("<html>safe</html>", encoding="utf-8")
    index_runs(tmp_path / "runs", tmp_path / "runs" / "observability.db")
    client = TestClient(create_dashboard(root_dir=tmp_path))

    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/runs").json()["runs"][0]["run_id"] == "run-1"
    events = client.get("/api/runs/run-1/events?after_id=1").json()["events"]
    assert [event["event_id"] for event in events] == [2]
    assert CANARY not in json.dumps(events)
    assert client.get("/api/artifacts", params={"run_id": "run-1", "path": "report.html"}).status_code == 200
    assert client.get("/api/artifacts", params={"run_id": "run-1", "path": "../secret.txt"}).status_code == 403


def test_operator_cli_migrates_graphs_and_indexes(tmp_path):
    legacy = tmp_path / "legacy.yaml"
    migrated = tmp_path / "workflow.yaml"
    migration_report = tmp_path / "migration.md"
    graph = tmp_path / "workflow_graph.json"
    runs = tmp_path / "runs"
    run = runs / "run-1"
    run.mkdir(parents=True)
    legacy.write_text(
        """
id: cli_flow
name: CLI Flow
version: "1"
type: api
steps:
  - id: read
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )
    (run / "run_manifest.json").write_text(
        json.dumps({"run_id": "run-1", "workflow": "cli_flow", "status": "passed", "run_directory": str(run)}),
        encoding="utf-8",
    )
    (run / "timeline.jsonl").write_text('{"run_id":"run-1","event":"run.finished","status":"passed"}\n', encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "main.py",
            "--migrate-workflow",
            str(legacy),
            "--workflow-output",
            str(migrated),
            "--migration-report",
            str(migration_report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            "main.py",
            "--workflow-graph",
            str(migrated),
            "--workflow-graph-output",
            str(graph),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    indexed = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--observability-index",
            "--runs-dir",
            str(runs),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    db_path = subprocess.run(
        [sys.executable, "main.py", "--observability-db-path", "--runs-dir", str(runs)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert migrated.exists()
    assert migration_report.exists()
    assert json.loads(graph.read_text(encoding="utf-8"))["summary"]["total_steps"] == 1
    assert "indexed_runs" in indexed.stdout
    assert db_path.stdout.strip().endswith("observability.db")
