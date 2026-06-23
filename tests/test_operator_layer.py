import json
import subprocess
import sys
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


def test_workflow_graph_cli_preserves_default_schema_metadata(tmp_path):
    workflow = tmp_path / "default_schema.yaml"
    workflow.write_text(
        """
schema_version: 2
name: human_gate_graph
targets:
  portal:
    type: browser
phases:
  - id: review
    steps:
      - id: approve
        target: portal
        type: human_gate
        choices:
          - approve
          - stop
        default_safe_action: stop
        action:
          type: no_op
        success_checks:
          - type: always_pass
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "main.py", "--workflow-graph", str(workflow)],
        check=True,
        capture_output=True,
        text=True,
    )
    graph = json.loads(completed.stdout)

    assert graph["summary"]["human_gates"] == 1
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


def test_operator_cli_migrates_graphs_and_reads_run_artifacts(tmp_path):
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
    (run / "logs.jsonl").write_text('{"run_id":"run-1","step":"read","status":"passed"}\n', encoding="utf-8")
    (run / "report.html").write_text("<html>ok</html>", encoding="utf-8")

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
    runs_list = subprocess.run(
        [sys.executable, "main.py", "--runs-list", "--runs-dir", str(runs)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_show = subprocess.run(
        [sys.executable, "main.py", "--runs-show", "run-1", "--runs-dir", str(runs)],
        check=True,
        capture_output=True,
        text=True,
    )
    logs_show = subprocess.run(
        [sys.executable, "main.py", "--logs-show", "run-1", "--runs-dir", str(runs)],
        check=True,
        capture_output=True,
        text=True,
    )
    report_open = subprocess.run(
        [sys.executable, "main.py", "--report-open", "run-1", "--runs-dir", str(runs)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert migrated.exists()
    assert migration_report.exists()
    assert json.loads(graph.read_text(encoding="utf-8"))["summary"]["total_steps"] == 1
    assert "run-1" in runs_list.stdout
    assert json.loads(run_show.stdout)["run_id"] == "run-1"
    assert json.loads(logs_show.stdout)["step"] == "read"
    assert report_open.stdout.strip().endswith("report.html")
