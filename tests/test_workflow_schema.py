"""Tests for YAML workflow validation and execution."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.rpa.yaml_runner import YamlWorkflowRunner
from harness.config import HarnessConfig
from harness.verification import validate_workflow


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
    assert result["failure_type"] == "config"
    assert result["missing_secrets"] == [{"name": "api_token", "env": "MISSING_API_TOKEN"}]


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
