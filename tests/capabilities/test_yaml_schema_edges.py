"""Capability characterization for YAML schema boundaries."""

from pathlib import Path

import pytest
import yaml

from harness.rpa.yaml_runner import YamlWorkflowRunner
from harness.verification import validate_workflow


class FakeNotifier:
    def __init__(self):
        self.events = []

    async def question(self, question: str, *, context: dict = None):
        self.events.append(("question", question, context))

    async def failure(self, message: str, *, context: dict = None, topic: str = "failures"):
        self.events.append(("failure", message, context))

    async def frustration(self, message: str, *, context: dict = None):
        self.events.append(("frustration", message, context))

    async def memory_note(self, message: str, *, context: dict = None):
        self.events.append(("memory_note", message, context))


def _workflow(workflow_type: str, steps: list[dict], **extra: object) -> dict:
    data = {
        "id": f"{workflow_type}_capability",
        "name": f"{workflow_type.title()} Capability",
        "version": "1.0",
        "type": workflow_type,
        "steps": steps,
    }
    data.update(extra)
    return data


def test_valid_browser_api_and_no_op_workflows_validate():
    browser = _workflow(
        "browser",
        [
            {
                "id": "open",
                "action": {"type": "browser.goto", "url": "file:///tmp/form.html"},
                "success_check": [{"type": "url_contains", "value": "form.html"}],
            },
            {
                "id": "read_heading",
                "action": {
                    "type": "browser.get_text",
                    "selector": {"strategy": "data-testid", "value": "heading"},
                    "output": "heading_text",
                },
                "success_check": [
                    {
                        "type": "variable_equals",
                        "value": {"var": "heading_text", "value": "Capability Form"},
                    }
                ],
            },
        ],
    )
    api = _workflow(
        "api",
        [
            {
                "id": "read",
                "action": {"type": "api.get", "url": "http://127.0.0.1:8765/read"},
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
    )
    no_op = _workflow(
        "mixed",
        [
            {
                "id": "documented_pause",
                "action": {"type": "no_op"},
                "allow_without_success_check": True,
            }
        ],
    )

    assert validate_workflow(browser) == []
    assert validate_workflow(api) == []
    assert validate_workflow(no_op) == []


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        (
            _workflow(
                "browser",
                [{"id": "missing_check", "action": {"type": "browser.get_title"}}],
            ),
            "missing success_check",
        ),
        (
            _workflow(
                "api",
                [
                    {
                        "id": "same",
                        "action": {"type": "api.get", "url": "http://127.0.0.1/read"},
                        "success_check": [{"type": "status_code", "value": 200}],
                    },
                    {
                        "id": "same",
                        "action": {"type": "api.get", "url": "http://127.0.0.1/read"},
                        "success_check": [{"type": "status_code", "value": 200}],
                    },
                ],
            ),
            "duplicate step id",
        ),
        (
            _workflow(
                "api",
                [
                    {
                        "id": "secret_header",
                        "action": {
                            "type": "api.get",
                            "url": "http://127.0.0.1/read",
                            "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                        },
                        "success_check": [{"type": "status_code", "value": 200}],
                    }
                ],
            ),
            "undeclared secret 'api_token'",
        ),
        (
            _workflow(
                "api",
                [
                    {
                        "id": "literal_secret",
                        "action": {
                            "type": "api.get",
                            "url": "http://127.0.0.1/read",
                            "headers": {"Authorization": "Bearer literal-token"},
                        },
                        "success_check": [{"type": "status_code", "value": 200}],
                    }
                ],
            ),
            "literal sensitive value",
        ),
        (
            _workflow(
                "api",
                [
                    {
                        "id": "secret_url",
                        "action": {
                            "type": "api.get",
                            "url": "http://127.0.0.1/read?token=${secrets.api_token}",
                        },
                        "success_check": [{"type": "status_code", "value": 200}],
                    }
                ],
                credentials={"api_token": "API_TOKEN"},
            ),
            "cannot use secrets in URL/path",
        ),
        (
            _workflow(
                "api",
                [
                    {
                        "id": "write",
                        "action": {
                            "type": "api.post",
                            "url": "http://127.0.0.1/write",
                            "json_data": {"ok": True},
                        },
                        "success_check": [{"type": "status_code", "value": 201}],
                    }
                ],
            ),
            "allow_destructive",
        ),
        (
            _workflow(
                "browser",
                [
                    {
                        "id": "bad_always_pass",
                        "action": {"type": "browser.get_title"},
                        "success_check": [{"type": "always_pass"}],
                    }
                ],
            ),
            "always_pass is only allowed for no_op",
        ),
        (
            _workflow(
                "browser",
                [
                    {
                        "id": "bad_field_check",
                        "action": {
                            "type": "browser.fill",
                            "selector": {"strategy": "label", "value": "Password"},
                            "value": "fixture-value",
                        },
                        "success_check": [{"type": "field_has_value", "redacted": True}],
                    }
                ],
            ),
            "field_has_value requires selector",
        ),
    ],
)
def test_invalid_yaml_schema_edges_fail_with_specific_errors(workflow, expected):
    errors = validate_workflow(workflow)

    assert any(expected in error for error in errors), errors


def test_mixed_browser_and_api_workflow_is_schema_supported():
    workflow = _workflow(
        "mixed",
        [
            {
                "id": "open",
                "action": {"type": "browser.goto", "url": "file:///tmp/form.html"},
                "success_check": [{"type": "url_contains", "value": "form.html"}],
            },
            {
                "id": "read",
                "action": {"type": "api.get", "url": "http://127.0.0.1:8765/read"},
                "success_check": [{"type": "status_code", "value": 200}],
            },
        ],
    )

    assert validate_workflow(workflow) == []


def test_yaml_runner_id_selector_uses_literal_attribute_selector():
    class Page:
        def __init__(self):
            self.selector = ""

        def locator(self, selector):
            self.selector = selector
            return object()

    runner = YamlWorkflowRunner()
    page = Page()

    runner._locator_from_selector(page, {"strategy": "id", "value": "ctl00:Main.login"})

    assert page.selector == '[id="ctl00:Main.login"]'


def test_yaml_runner_request_failed_accepts_string_failure():
    class Page:
        def __init__(self):
            self.handlers = {}

        def on(self, event, handler):
            self.handlers[event] = handler

    class Driver:
        def __init__(self):
            self.page = Page()

    class Request:
        url = "https://example.test/path?token=secret"
        method = "GET"
        failure = "net::ERR_FAILED token=secret"

    runner = YamlWorkflowRunner()
    runner._secrets = {"api_token": "secret"}
    driver = Driver()

    runner._attach_browser_evidence_handlers(driver)
    driver.page.handlers["requestfailed"](Request())

    assert runner._network_entries == [
        {
            "url": "https://example.test/path",
            "method": "GET",
            "error_text": "net::ERR_FAILED token=[REDACTED]",
        }
    ]


def test_yaml_runner_redacts_runtime_errors_with_workflow_secrets():
    runner = YamlWorkflowRunner()
    runner._secrets = {"api_token": "super-secret-token"}

    assert (
        runner._redact_runtime_text("expected super-secret-token in response")
        == "expected [REDACTED] in response"
    )


def test_yaml_runner_only_announces_successful_memory_writes():
    assert YamlWorkflowRunner._memory_write_succeeded({"status": "stored", "id": 1}) is True
    assert YamlWorkflowRunner._memory_write_succeeded({"status": "disabled"}) is False
    assert YamlWorkflowRunner._memory_write_succeeded({"available": False}) is False


@pytest.mark.asyncio
async def test_yaml_runner_asks_question_when_required_secret_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("CAPABILITY_API_TOKEN", raising=False)
    workflow = _workflow(
        "api",
        [
            {
                "id": "read_with_secret",
                "action": {
                    "type": "api.get",
                    "url": "http://127.0.0.1:8765/read",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [{"type": "status_code", "value": 200}],
            }
        ],
        credentials={"api_token": "CAPABILITY_API_TOKEN"},
    )
    path = tmp_path / "missing_secret.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    runner = YamlWorkflowRunner()
    notifier = FakeNotifier()
    runner.notifier = notifier

    result = await runner.run(str(path))

    assert result["status"] == "failed"
    assert result["failure_type"] == "config"
    assert notifier.events == [
        (
            "question",
            "I cannot start this YAML workflow because required secrets are missing.",
            {"workflow": "Api Capability", "missing": "api_token"},
        )
    ]


@pytest.mark.asyncio
async def test_desktop_yaml_is_schema_supported_but_platform_blocked_on_non_windows(tmp_path: Path):
    workflow = _workflow(
        "desktop",
        [
            {
                "id": "click_window",
                "action": {
                    "type": "desktop.click",
                    "selector": {"strategy": "automation_id", "value": "Submit"},
                },
                "success_check": [
                    {
                        "type": "element_exists",
                        "selector": {"strategy": "automation_id", "value": "Submit"},
                    }
                ],
            }
        ],
    )
    assert validate_workflow(workflow) == []
    path = tmp_path / f"{workflow['type']}.yaml"
    path.write_text(yaml.safe_dump(workflow))

    result = await YamlWorkflowRunner().run(str(path))

    assert result["status"] == "failed"
    assert result["failure_type"] == "execution"
    assert "Desktop YAML runtime requires Windows UIAutomation" in result["reason"]
