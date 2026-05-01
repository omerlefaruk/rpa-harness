"""Capability characterization for YAML API runtime execution."""

import json
from pathlib import Path
from typing import Optional

import pytest
import yaml

from harness.reporting.failure_report import FailureReport
from harness.rpa.yaml_runner import YamlWorkflowRunner


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = '{"id": 1, "message": "capability ok"}',
        url: str = "http://127.0.0.1:8765/read?token=should-not-leak",
    ):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = {
            "content-type": "application/json",
            "set-cookie": "session=should-not-leak",
        }

    def json(self):
        return json.loads(self.text)


class FakeAPIDriver:
    def __init__(self, response: Optional[FakeResponse] = None):
        self.response = response or FakeResponse()
        self.calls: list[dict] = []

    async def launch(self):
        return None

    async def get(self, path, params=None, headers=None):
        self.calls.append(
            {"method": "GET", "path": path, "params": params, "headers": headers or {}}
        )
        return self.response

    async def delete(self, path, params=None, headers=None):
        self.calls.append(
            {"method": "DELETE", "path": path, "params": params, "headers": headers or {}}
        )
        return self.response

    async def _request(self, method, path, **kwargs):
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.response

    async def close(self):
        return None


def _write_workflow(tmp_path: Path, workflow: dict) -> Path:
    path = tmp_path / f"{workflow['id']}.yaml"
    path.write_text(yaml.safe_dump(workflow))
    return path


async def _run_with_fake_api(tmp_path: Path, workflow: dict, fake: FakeAPIDriver):
    runner = YamlWorkflowRunner()
    runner.failure = FailureReport(str(tmp_path / "runs"))

    async def get_fake_api():
        runner._drivers["api"] = fake
        return fake

    runner._get_api_driver = get_fake_api
    return await runner.run(str(_write_workflow(tmp_path, workflow)))


@pytest.mark.asyncio
async def test_api_get_checks_status_json_path_and_response_contains(tmp_path):
    fake = FakeAPIDriver(
        FakeResponse(text='{"id": 7, "message": "capability ok", "items": [{"name": "alpha"}]}')
    )
    workflow = {
        "id": "api_read_capability",
        "name": "API Read Capability",
        "version": "1.0",
        "type": "api",
        "steps": [
            {
                "id": "read_item",
                "action": {
                    "type": "api.get",
                    "base_url": "http://127.0.0.1:8765",
                    "path": "/read",
                    "params": {"q": "alpha"},
                },
                "success_check": [
                    {"type": "status_code", "value": 200},
                    {
                        "type": "json_path_equals",
                        "value": {"path": "$.items[0].name", "value": "alpha"},
                    },
                    {"type": "response_contains", "value": "capability ok"},
                ],
            }
        ],
    }

    result = await _run_with_fake_api(tmp_path, workflow, fake)

    assert result["status"] == "passed"
    assert fake.calls == [
        {
            "method": "GET",
            "path": "http://127.0.0.1:8765/read",
            "params": {"q": "alpha"},
            "headers": {},
        }
    ]


@pytest.mark.asyncio
async def test_api_post_requires_allow_destructive_and_executes_when_allowed(tmp_path):
    fake = FakeAPIDriver(FakeResponse(status_code=201, text='{"created": true}'))
    workflow = {
        "id": "api_write_capability",
        "name": "API Write Capability",
        "version": "1.0",
        "type": "api",
        "allow_destructive": True,
        "steps": [
            {
                "id": "create_item",
                "action": {
                    "type": "api.post",
                    "url": "http://127.0.0.1:8765/write",
                    "json_data": {"name": "fixture"},
                },
                "success_check": [
                    {"type": "status_code", "value": 201},
                    {"type": "json_path_equals", "value": {"path": "$.created", "value": True}},
                ],
            }
        ],
    }

    result = await _run_with_fake_api(tmp_path, workflow, fake)

    assert result["status"] == "passed"
    assert fake.calls[0]["method"] == "POST"
    assert fake.calls[0]["json"] == {"name": "fixture"}
    assert result["steps"][0]["destructive"] is True


@pytest.mark.asyncio
async def test_missing_secret_preflight_fails_before_api_execution(tmp_path, monkeypatch):
    monkeypatch.delenv("CAPABILITY_API_TOKEN", raising=False)
    fake = FakeAPIDriver()
    workflow = {
        "id": "missing_secret_capability",
        "name": "Missing Secret Capability",
        "version": "1.0",
        "type": "api",
        "credentials": {"api_token": "CAPABILITY_API_TOKEN"},
        "steps": [
            {
                "id": "read_item",
                "action": {
                    "type": "api.get",
                    "url": "http://127.0.0.1:8765/read",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    }

    result = await _run_with_fake_api(tmp_path, workflow, fake)

    assert result["status"] == "failed"
    assert result["failure_type"] == "config"
    assert result["missing_secrets"] == [{"name": "api_token", "env": "CAPABILITY_API_TOKEN"}]
    assert fake.calls == []


@pytest.mark.asyncio
async def test_authorization_secret_is_used_but_not_leaked_in_result(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPABILITY_API_TOKEN", "real-token-for-redaction")
    fake = FakeAPIDriver(
        FakeResponse(text='{"id": 1, "message": "capability ok", "echo": "real-token-for-redaction"}')
    )
    workflow = {
        "id": "api_secret_runtime",
        "name": "API Secret Runtime",
        "version": "1.0",
        "type": "api",
        "credentials": {"api_token": "CAPABILITY_API_TOKEN"},
        "steps": [
            {
                "id": "read_item",
                "action": {
                    "type": "api.get",
                    "url": "http://127.0.0.1:8765/read",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    }

    result = await _run_with_fake_api(tmp_path, workflow, fake)

    assert result["status"] == "passed"
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer real-token-for-redaction"
    assert "real-token-for-redaction" not in json.dumps(result, default=str)


@pytest.mark.asyncio
async def test_api_failure_report_has_sanitized_redacted_response_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPABILITY_API_TOKEN", "real-token-for-redaction")
    fake = FakeAPIDriver(
        FakeResponse(
            status_code=500,
            text='{"error": "boom", "echo": "real-token-for-redaction"}',
            url="http://127.0.0.1:8765/read?token=real-token-for-redaction&debug=true",
        )
    )
    workflow = {
        "id": "api_failure_evidence",
        "name": "API Failure Evidence",
        "version": "1.0",
        "type": "api",
        "credentials": {"api_token": "CAPABILITY_API_TOKEN"},
        "steps": [
            {
                "id": "read_item",
                "action": {
                    "type": "api.get",
                    "url": "http://127.0.0.1:8765/read",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    }

    result = await _run_with_fake_api(tmp_path, workflow, fake)

    report_path = Path(result["failure_report"])
    report = json.loads(report_path.read_text())
    api_response_path = report_path.parent / report["evidence"]["api_response"]
    api_response = json.loads(api_response_path.read_text())

    assert result["status"] == "failed"
    assert report["repro_command"].endswith("api_failure_evidence.yaml")
    assert api_response["status_code"] == 500
    assert api_response["url"] == "http://127.0.0.1:8765/read"
    assert api_response["headers"]["set-cookie"] == "[REDACTED]"
    assert "real-token-for-redaction" not in report_path.read_text()
    assert "real-token-for-redaction" not in api_response_path.read_text()


def test_api_response_context_sanitizes_url_headers_and_body(monkeypatch):
    monkeypatch.setenv("CAPABILITY_API_TOKEN", "real-token-for-redaction")
    runner = YamlWorkflowRunner()
    runner._secrets = {"api_token": "real-token-for-redaction"}
    response = FakeResponse(
        status_code=500,
        text='{"error": "boom", "echo": "real-token-for-redaction"}',
        url="http://127.0.0.1:8765/read?token=real-token-for-redaction&debug=true",
    )

    context = runner._api_response_context(response)

    assert context["status_code"] == 500
    assert context["url"] == "http://127.0.0.1:8765/read"
    assert context["response_headers"]["set-cookie"] == "[REDACTED]"
    assert "real-token-for-redaction" not in context["body_preview"]
