"""Tests for YAML workflow validation and execution."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.rpa.yaml_runner import YamlWorkflowRunner
from harness.config import HarnessConfig
from harness.verification import preflight_workflow, validate_workflow


def test_validate_minimal_workflow():
    wf_path = Path(__file__).parent.parent / "workflows" / "examples" / "minimal_example.yaml"
    if not wf_path.exists():
        pytest.skip("minimal_example.yaml not found")
    import yaml

    wf = yaml.safe_load(wf_path.read_text())
    errors = validate_workflow(wf)
    assert len(errors) == 0, f"Validation errors: {errors}"


def test_validate_browser_login_workflow():
    wf_path = Path(__file__).parent.parent / "workflows" / "examples" / "browser_login_example.yaml"
    if not wf_path.exists():
        pytest.skip("browser_login_example.yaml not found")
    import yaml

    wf = yaml.safe_load(wf_path.read_text())
    errors = validate_workflow(wf)
    assert len(errors) == 0, f"Validation errors: {errors}"


def test_validate_excel_workflow():
    wf_path = Path(__file__).parent.parent / "workflows" / "examples" / "excel_row_example.yaml"
    if not wf_path.exists():
        pytest.skip("excel_row_example.yaml not found")
    import yaml

    wf = yaml.safe_load(wf_path.read_text())
    errors = validate_workflow(wf)
    assert len(errors) == 0, f"Validation errors: {errors}"


def test_validate_invalid_workflow():
    wf = {
        "id": "bad",
        "name": "Bad",
        "version": "1.0",
        "type": "browser",
        "steps": [
            {
                "id": "s1",
                "action": {"type": "browser.click"},
            }
        ],
    }
    errors = validate_workflow(wf)
    assert any("missing success_check" in error for error in errors)
    assert any("requires selector" in error for error in errors)


def test_validate_unknown_action_fails():
    wf = {
        "id": "bad",
        "name": "Bad",
        "version": "1.0",
        "type": "browser",
        "steps": [
            {
                "id": "s1",
                "action": {"type": "browser.fake"},
                "success_check": [{"type": "always_pass"}],
            }
        ],
    }
    errors = validate_workflow(wf)
    assert any("unknown action type" in error for error in errors)


def test_validate_secret_reference_must_be_declared():
    wf = {
        "id": "bad",
        "name": "Bad",
        "version": "1.0",
        "type": "api",
        "steps": [
            {
                "id": "s1",
                "action": {
                    "type": "api.get",
                    "url": "https://example.com",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    }
    errors = validate_workflow(wf)
    assert any("undeclared secret 'api_token'" in error for error in errors)


def test_validate_rejects_secret_in_inputs():
    wf = {
        "id": "bad",
        "name": "Bad",
        "version": "1.0",
        "type": "api",
        "inputs": {"token": "${secrets.api_token}"},
        "credentials": {"api_token": "API_TOKEN"},
        "steps": [
            {
                "id": "s1",
                "action": {"type": "api.get", "url": "https://example.com"},
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    }
    errors = validate_workflow(wf)
    assert any("secrets are not allowed in inputs" in error for error in errors)


def test_validate_destructive_api_requires_allow_destructive():
    wf = {
        "id": "bad",
        "name": "Bad",
        "version": "1.0",
        "type": "api",
        "steps": [
            {
                "id": "s1",
                "action": {
                    "type": "api.post",
                    "url": "https://example.com",
                    "json_data": {"ok": True},
                },
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    }
    errors = validate_workflow(wf)
    assert any("allow_destructive" in error for error in errors)


def test_validate_side_effecting_retry_requires_idempotency_guard():
    wf = {
        "id": "bad_retry",
        "name": "Bad Retry",
        "version": "1.0",
        "type": "api",
        "allow_destructive": True,
        "steps": [
            {
                "id": "write",
                "failure_class": "transient",
                "action": {
                    "type": "api.post",
                    "url": "https://example.com",
                    "json_data": {"ok": True},
                },
                "success_check": [{"type": "status_code", "value": 201}],
                "recovery": [{"type": "retry", "max_attempts": 2}],
            }
        ],
    }

    errors = validate_workflow(wf)

    assert any("retry requires transient failure class" in error for error in errors)


def test_validate_side_effecting_retry_allows_idempotency_guard():
    wf = {
        "id": "safe_retry",
        "name": "Safe Retry",
        "version": "1.0",
        "type": "api",
        "allow_destructive": True,
        "steps": [
            {
                "id": "write",
                "failure_class": "transient",
                "idempotency_key": "request_id",
                "action": {
                    "type": "api.post",
                    "url": "https://example.com",
                    "json_data": {"ok": True},
                },
                "success_check": [{"type": "status_code", "value": 201}],
                "recovery": [{"type": "retry", "max_attempts": 2}],
            }
        ],
    }

    errors = validate_workflow(wf)

    assert errors == []


def test_yaml_runner_workflow_inputs_override_default_config_variables():
    config = HarnessConfig(variables={"base_url": "https://default.example"})
    runner = YamlWorkflowRunner(config=config)

    resolved = runner._resolve_inputs({"base_url": "https://workflow.example"})

    assert resolved["base_url"] == "https://workflow.example"


def test_yaml_runner_resolves_pwd_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("PWD", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = YamlWorkflowRunner()

    assert runner._resolve_string("file://${PWD}/fixture.html") == (
        f"{tmp_path.as_uri()}/fixture.html"
    )
    assert runner._resolve_string("file://$PWD/fixture.html") == (
        f"{tmp_path.as_uri()}/fixture.html"
    )
    assert runner._resolve_string("${PWD}/fixture.html") == (
        f"{tmp_path.as_posix()}/fixture.html"
    )


def test_yaml_runner_pwd_fallback_does_not_rewrite_longer_variable_names(tmp_path, monkeypatch):
    monkeypatch.delenv("PWD", raising=False)
    monkeypatch.delenv("PWD_SUFFIX", raising=False)
    monkeypatch.chdir(tmp_path)
    runner = YamlWorkflowRunner()

    assert runner._resolve_string("$PWD_SUFFIX/${PWD_SUFFIX}/$PWD/file.txt") == (
        f"$PWD_SUFFIX/${{PWD_SUFFIX}}/{tmp_path.as_posix()}/file.txt"
    )
    assert runner._resolve_string("file://$PWD_SUFFIX/fixture.html") == (
        "file://$PWD_SUFFIX/fixture.html"
    )


@pytest.mark.asyncio
async def test_yaml_runner_load():
    wf_path = Path(__file__).parent.parent / "workflows" / "examples" / "minimal_example.yaml"
    if not wf_path.exists():
        pytest.skip("minimal_example.yaml not found")
    runner = YamlWorkflowRunner()
    wf = runner.load(str(wf_path))
    assert wf["id"] == "minimal_example"
    assert len(wf["steps"]) == 3


@pytest.mark.asyncio
async def test_yaml_runner_run(tmp_path):
    wf_path = tmp_path / "noop.yaml"
    wf_path.write_text("""
id: noop_test
name: Noop Test
version: "1.0"
type: api
steps:
  - id: done
    action:
      type: no_op
    success_check:
      - type: always_pass
""")
    runner = YamlWorkflowRunner()
    result = await runner.run(str(wf_path))
    assert result["status"] == "passed"
    assert result["steps_completed"] > 0
    assert "rulebook_audit" in result
    assert result["rulebook_audit"]["score"] < 5


@pytest.mark.asyncio
async def test_yaml_runner_writes_operator_artifacts_for_passed_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "noop.yaml"
    wf_path.write_text("""
id: noop_artifacts
name: Noop Artifacts
version: "1.0"
type: api
steps:
  - id: done
    phase: login
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    result = await YamlWorkflowRunner().run(str(wf_path))

    run_dir = Path(result["run_dir"])
    events = [json.loads(line)["event"] for line in (run_dir / "timeline.jsonl").read_text().splitlines()]
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert result["status"] == "passed"
    assert (run_dir / "preflight.json").exists()
    assert (run_dir / "report.html").exists()
    assert manifest["status"] == "passed"
    assert manifest["summary"]["total_phases"] == 1
    assert "run.started" in events
    assert "step.passed" in events
    assert "run.finished" in events


@pytest.mark.asyncio
async def test_yaml_runner_writes_records_for_record_steps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "recorded.yaml"
    wf_path.write_text("""
id: recorded_steps
name: Recorded Steps
version: "1.0"
type: api
steps:
  - id: validate_record
    phase: process_records
    record_id: INV-1001
    row_number: 2
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    result = await YamlWorkflowRunner().run(str(wf_path))

    run_dir = Path(result["run_dir"])
    records = [
        json.loads(line)
        for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    report_html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert [record["status"] for record in records] == ["running", "passed"]
    assert manifest["records"] == "records.jsonl"
    assert manifest["summary"]["total_records"] == 1
    assert manifest["summary"]["passed_records"] == 1
    assert report["records"][-1]["record_id"] == "INV-1001"
    assert "Record table" in report_html


@pytest.mark.asyncio
async def test_yaml_runner_only_record_filters_steps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "records.yaml"
    wf_path.write_text("""
id: only_record
name: Only Record
version: "1.0"
type: api
steps:
  - id: first
    record_id: A
    action:
      type: no_op
    success_check:
      - type: always_pass
  - id: second
    record_id: B
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    result = await YamlWorkflowRunner().run(str(wf_path), only_record="B")

    assert result["status"] == "passed"
    assert [step["step_id"] for step in result["steps"]] == ["second"]


@pytest.mark.asyncio
async def test_yaml_runner_only_record_filters_for_each_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "loop_records.yaml"
    wf_path.write_text("""
id: loop_records
name: Loop Records
version: "1.0"
type: api
inputs:
  rows:
    - invoice_id: A
    - invoice_id: B
steps:
  - id: process_row
    phase: process_records
    for_each:
      input: rows
      record_id: invoice_id
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    result = await YamlWorkflowRunner().run(str(wf_path), only_record="B")

    assert result["status"] == "passed"
    assert [step["record_id"] for step in result["steps"]] == ["B"]


@pytest.mark.asyncio
async def test_retry_run_retries_only_safe_failed_records(tmp_path, monkeypatch):
    from harness.reporting.run_artifacts import retry_run

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "retry.yaml"
    wf_path.write_text("""
id: retry_records
name: Retry Records
version: "1.0"
type: api
steps:
  - id: safe_failed
    record_id: SAFE
    action:
      type: no_op
    success_check:
      - type: always_pass
  - id: unsafe_failed
    record_id: UNSAFE
    side_effect: external_write
    action:
      type: no_op
    success_check:
      - type: always_pass
""")
    run_dir = tmp_path / "runs" / "old-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"run_id": "old-run", "workflow_path": str(wf_path)}),
        encoding="utf-8",
    )
    (run_dir / "records.jsonl").write_text(
        "\n".join(
            [
                json.dumps({
                    "record_id": "SAFE",
                    "status": "failed",
                    "safe_retry": {"status": "yes"},
                }),
                json.dumps({
                    "record_id": "UNSAFE",
                    "status": "failed",
                    "safe_retry": {"status": "no"},
                }),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = await retry_run("old-run", failed_records=True)

    assert result["status"] == "passed"
    assert result["retried_records"] == ["SAFE"]
    assert [step["step_id"] for step in result["results"][0]["steps"]] == ["safe_failed"]


@pytest.mark.asyncio
async def test_yaml_runner_phase_and_pause_controls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "phases.yaml"
    wf_path.write_text("""
id: phase_controls
name: Phase Controls
version: "1.0"
type: api
steps:
  - id: open_login
    phase: login
    action:
      type: no_op
    success_check:
      - type: always_pass
  - id: submit_invoice
    phase: process_records
    side_effect: external_write
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    phase_result = await YamlWorkflowRunner().run(str(wf_path), phase="login")
    paused = await YamlWorkflowRunner().run(str(wf_path), pause_before="submit_invoice")

    assert [step["step_id"] for step in phase_result["steps"]] == ["open_login"]
    assert paused["status"] == "paused"
    assert [step["step_id"] for step in paused["steps"]] == ["open_login"]
    assert json.loads((Path(paused["run_dir"]) / "run_manifest.json").read_text())["status"] == "blocked"


@pytest.mark.asyncio
async def test_yaml_runner_copilot_pause_asks_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "copilot.yaml"
    wf_path.write_text("""
id: copilot_pause
name: Copilot Pause
version: "1.0"
type: api
steps:
  - id: open_login
    phase: login
    action:
      type: no_op
    success_check:
      - type: always_pass
  - id: submit_invoice
    phase: process_records
    side_effect: external_write
    action:
      type: no_op
    success_check:
      - type: always_pass
""")
    config = HarnessConfig()
    config.copilot_enabled = True

    class FakeCopilot:
        def __init__(self):
            self.questions = []

        async def ask(self, **kwargs):
            self.questions.append(kwargs)
            return {"action": "continue", "answer": "continue", "question_id": "q-1"}

    runner = YamlWorkflowRunner(config)
    fake = FakeCopilot()
    runner._copilot = fake

    result = await runner.run(str(wf_path), pause_before="submit_invoice")

    assert result["status"] == "passed"
    assert [step["step_id"] for step in result["steps"]] == ["open_login", "submit_invoice"]
    assert fake.questions[0]["step"]["id"] == "submit_invoice"
    timeline = (Path(result["run_dir"]) / "timeline.jsonl").read_text(encoding="utf-8")
    assert "copilot.question" in timeline
    assert "copilot.answer" in timeline


def test_audit_workflow_cli_outputs_rulebook_json(tmp_path):
    wf_path = tmp_path / "noop.yaml"
    wf_path.write_text("""
id: noop_cli_audit
name: Noop CLI Audit
version: "1.0"
type: api
steps:
  - id: done
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    completed = subprocess.run(
        [sys.executable, "main.py", "--audit-workflow", str(wf_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["workflow_id"] == "noop_cli_audit"
    assert payload["validation_status"] == "valid"
    assert "rulebook_audit" in payload


def test_validate_yaml_cli_outputs_workflow_summary(tmp_path):
    wf_path = tmp_path / "noop.yaml"
    wf_path.write_text("""
id: noop_cli_validate
name: Noop CLI Validate
version: "1.0"
type: api
steps:
  - id: done
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    completed = subprocess.run(
        [sys.executable, "main.py", "--validate-yaml", str(wf_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "VALID: noop_cli_validate (1 steps)" in completed.stdout


def test_run_artifact_cli_helpers(tmp_path, monkeypatch, capsys):
    from harness.builder import capture_desktop_session, validate_discovery_fixtures
    from harness.reporting.run_artifacts import print_run_logs, run_report_path
    from main import _start_builder_session

    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    (run_dir / "logs.jsonl").write_text(
        '{"step":"one","message":"first"}\n{"step":"two","message":"second"}\n',
        encoding="utf-8",
    )
    task = tmp_path / "task.md"
    task.write_text("Build login flow with token=secret-value", encoding="utf-8")

    print_run_logs("run-1", tail=1, step=None)
    output = capsys.readouterr().out
    assert "second" in output
    assert "first" not in output
    assert run_report_path("run-1") == (run_dir / "report.html").resolve()

    session = _start_builder_session(str(task), "session-1")
    assert (session / "task_spec.md").exists()
    assert "secret-value" not in (session / "task_spec.md").read_text(encoding="utf-8")
    assert (session / "discovery_session.json").exists()

    capture = capture_desktop_session(app="Legacy ERP", session_dir=session)
    assert (capture / "capture_session.json").exists()
    assert "blocked" in (capture / "capture_session.json").read_text(encoding="utf-8")

    fixture = tmp_path / "workflows" / "capabilities"
    fixture.mkdir(parents=True)
    (fixture / "local_browser_form.html").write_text("<form></form>", encoding="utf-8")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "dump_uia_tree.py").write_text("# fixture", encoding="utf-8")
    discovery = validate_discovery_fixtures(tmp_path)
    assert discovery["browser_fixture"]["status"] == "passed"
    assert discovery["desktop_fixture"]["status"] == "blocked"


def test_validate_workflow_tool_outputs_valid_json(tmp_path):
    wf_path = tmp_path / "noop.yaml"
    wf_path.write_text("""
id: noop_tool_validate
name: Noop Tool Validate
version: "1.0"
type: api
steps:
  - id: done
    action:
      type: no_op
    success_check:
      - type: always_pass
""")

    completed = subprocess.run(
        [sys.executable, "tools/validate_workflow.py", str(wf_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "valid"
    assert payload["workflow_id"] == "noop_tool_validate"
    assert payload["step_count"] == 1
    assert payload["total_steps"] == 1
    assert payload["steps_with_success_checks"] == 1


def test_preflight_blocks_missing_input_file(tmp_path):
    missing = tmp_path / "missing.xlsx"
    workflow = {
        "id": "missing_file",
        "name": "Missing File",
        "version": "1.0",
        "type": "excel",
        "inputs": {"workbook": str(missing)},
        "steps": [
            {
                "id": "read",
                "action": {"type": "excel.read", "path": "${inputs.workbook}"},
                "success_check": [{"type": "variable_has_value", "value": "rows"}],
            }
        ],
    }

    result = preflight_workflow(workflow)

    assert result["status"] == "failed"
    assert any("input file does not exist" in error for error in result["blocking_errors"])


def test_preflight_blocks_missing_excel_required_column(tmp_path):
    import openpyxl

    workbook_path = tmp_path / "input.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["invoice_id"])
    workbook.save(workbook_path)

    workflow = {
        "id": "bad_columns",
        "name": "Bad Columns",
        "version": "1.0",
        "type": "excel",
        "inputs": {"workbook": str(workbook_path)},
        "input": {"required_columns": ["invoice_id", "amount"]},
        "steps": [
            {
                "id": "read",
                "action": {"type": "excel.read", "path": "${inputs.workbook}"},
                "success_check": [{"type": "variable_has_value", "value": "rows"}],
            }
        ],
    }

    result = preflight_workflow(workflow)

    assert result["status"] == "failed"
    assert any("missing required column 'amount'" in error for error in result["blocking_errors"])


@pytest.mark.asyncio
async def test_yaml_runner_missing_secret_preflight(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_API_TOKEN", raising=False)
    wf_path = tmp_path / "missing_secret.yaml"
    wf_path.write_text("""
id: missing_secret
name: Missing Secret
version: "1.0"
type: api
credentials:
  api_token: MISSING_API_TOKEN
steps:
  - id: get_data
    action:
      type: api.get
      url: "https://example.com/data"
      headers:
        Authorization: "Bearer ${secrets.api_token}"
    success_check:
      - type: status_code
        value: 200
""")

    result = await YamlWorkflowRunner().run(str(wf_path))
    assert result["status"] == "failed"
    assert result["state"] == "needs_operator_input"
    assert result["failure_type"] == "config"
    assert result["missing_secrets"] == [{"name": "api_token", "env": "MISSING_API_TOKEN"}]


@pytest.mark.asyncio
async def test_yaml_runner_missing_input_file_preflight(tmp_path):
    wf_path = tmp_path / "missing_file.yaml"
    wf_path.write_text(f"""
id: missing_file_preflight
name: Missing File Preflight
version: "1.0"
type: excel
inputs:
  workbook: "{(tmp_path / 'missing.xlsx').as_posix()}"
steps:
  - id: read_rows
    action:
      type: excel.read
      path: "${{inputs.workbook}}"
      output: rows
    success_check:
      - type: variable_has_value
        value: rows
""")

    result = await YamlWorkflowRunner().run(str(wf_path))

    assert result["status"] == "failed"
    assert result["failure_type"] == "preflight"
    assert any("input file does not exist" in error for error in result["preflight"]["blocking_errors"])


@pytest.mark.asyncio
async def test_yaml_runner_api_uses_logical_secret_with_fake_driver(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_API_TOKEN", "real-token")
    wf_path = tmp_path / "api.yaml"
    wf_path.write_text("""
id: api_secret
name: API Secret
version: "1.0"
type: api
credentials:
  api_token: TEST_API_TOKEN
steps:
  - id: get_data
    action:
      type: api.get
      base_url: "https://api.example.test"
      path: "/items/1"
      headers:
        Authorization: "Bearer ${secrets.api_token}"
    success_check:
      - type: status_code
        value: 200
      - type: json_path_equals
        value:
          path: "$.id"
          value: "1"
""")

    fake = FakeAPIDriver()
    runner = YamlWorkflowRunner()

    async def get_fake_api():
        runner._drivers["api"] = fake
        return fake

    runner._get_api_driver = get_fake_api
    result = await runner.run(str(wf_path))

    assert result["status"] == "passed"
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer real-token"
    assert "real-token" not in json.dumps(result)


@pytest.mark.asyncio
async def test_yaml_runner_failure_report_for_api_verification_failure(tmp_path):
    wf_path = tmp_path / "api_fail.yaml"
    wf_path.write_text("""
id: api_failure
name: API Failure
version: "1.0"
type: api
steps:
  - id: get_data
    action:
      type: api.get
      url: "https://api.example.test/items/1"
    success_check:
      - type: status_code
        value: 200
""")

    fake = FakeAPIDriver(response=FakeResponse(status_code=500, text='{"error": "boom"}'))
    runner = YamlWorkflowRunner()

    async def get_fake_api():
        runner._drivers["api"] = fake
        return fake

    runner._get_api_driver = get_fake_api
    result = await runner.run(str(wf_path))

    report_path = Path(result["failure_report"])
    report = json.loads(report_path.read_text())
    assert result["status"] == "failed"
    assert report_path.exists()
    assert report["failed_step_id"] == "get_data"
    assert "api_response" in report["evidence"]
    assert (report_path.parent / "logs.jsonl").exists()


@pytest.mark.asyncio
async def test_yaml_runner_failed_run_artifacts_are_redacted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "api_fail.yaml"
    wf_path.write_text("""
id: api_failure_redacted
name: API Failure Redacted
version: "1.0"
type: api
steps:
  - id: get_data
    phase: fetch
    action:
      type: api.get
      url: "https://api.example.test/items/1"
    success_check:
      - type: status_code
        value: 200
""")

    canary = "sk-test-canary-12345"
    fake = FakeAPIDriver(response=FakeResponse(status_code=500, text=f'{{"error": "token={canary}"}}'))
    runner = YamlWorkflowRunner()

    async def get_fake_api():
        runner._drivers["api"] = fake
        return fake

    runner._get_api_driver = get_fake_api
    result = await runner.run(str(wf_path))

    run_dir = Path(result["run_dir"])
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    report_html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert result["status"] == "failed"
    assert (run_dir / "evidence_bundle.json").exists()
    assert (run_dir / "repair_packet.json").exists()
    assert "verification_failed" in (run_dir / "timeline.jsonl").read_text()
    assert report["failure_kind_summary"] == [
        {
            "failure_kind": "verification_failed",
            "count": 1,
            "phases": ["fetch"],
            "steps": ["get_data"],
            "recommendation": (
                "Check whether the action succeeded, the target rejected it, "
                "or the success check is wrong."
            ),
        }
    ]
    assert "Failure kind summary" in report_html
    assert "verification_failed" in report_html
    for artifact in [
        "run_manifest.json",
        "preflight.json",
        "timeline.jsonl",
        "failure_report.json",
        "evidence_bundle.json",
        "repair_packet.json",
        "logs.jsonl",
        "report.json",
        "report.html",
        "artifacts/api_response.json",
    ]:
        assert canary not in (run_dir / artifact).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status_code=200, text='{"id": 1, "ok": true}'):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": "application/json"}
        self.url = "https://api.example.test/items/1?token=not-reported"

    def json(self):
        return json.loads(self.text)


class FakeAPIDriver:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or FakeResponse()

    async def get(self, path, params=None, headers=None):
        self.calls.append({"method": "GET", "path": path, "params": params, "headers": headers})
        return self.response

    async def close(self):
        pass
