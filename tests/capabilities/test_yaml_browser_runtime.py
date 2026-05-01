"""Opt-in capability characterization for real YAML browser runtime execution."""

import json
import os
from pathlib import Path

import pytest
import yaml

from harness.config import HarnessConfig
from harness.reporting.failure_report import FailureReport
from harness.rpa.yaml_runner import YamlWorkflowRunner

pytestmark = pytest.mark.skipif(
    os.getenv("RPA_RUN_INTEGRATION") != "1",
    reason="Set RPA_RUN_INTEGRATION=1 and install Playwright/browser binaries to run browser capability tests.",
)


def _local_form_page(tmp_path: Path) -> Path:
    page = tmp_path / "local_browser_form.html"
    page.write_text(
        """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Capability Fixture</title>
  <style>
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <h1 data-testid="heading">Capability Form</h1>
  <form id="fixture-form">
    <label for="name">Name</label>
    <input id="name" name="name" type="text">

    <label for="password">Password</label>
    <input id="password" name="password" type="password">

    <label for="plan">Plan</label>
    <select id="plan" name="plan">
      <option value="">Choose</option>
      <option value="basic">Basic</option>
      <option value="pro">Pro</option>
    </select>

    <label>
      <input id="toggle" name="toggle" type="checkbox">
      Show advanced
    </label>

    <section data-testid="advanced-panel" hidden>Advanced section ready</section>
    <div data-testid="press-marker" hidden>Enter was pressed</div>
    <button type="button" data-testid="submit-button">Save</button>
    <p data-testid="success" hidden>Saved</p>
  </form>
  <script>
    document.querySelector("#name").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        document.querySelector("[data-testid='press-marker']").hidden = false;
      }
    });
    document.querySelector("#toggle").addEventListener("change", (event) => {
      document.querySelector("[data-testid='advanced-panel']").hidden = !event.target.checked;
    });
    document.querySelector("[data-testid='submit-button']").addEventListener("click", () => {
      document.querySelector("[data-testid='success']").hidden = false;
      window.location.hash = "submitted";
    });
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )
    return page


def _write_workflow(tmp_path: Path, workflow: dict) -> Path:
    path = tmp_path / f"{workflow['id']}.yaml"
    path.write_text(yaml.safe_dump(workflow))
    return path


def _refresh_recovery_page(tmp_path: Path) -> Path:
    page = tmp_path / "refresh_recovery.html"
    page.write_text(
        """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Refresh Recovery Fixture</title>
</head>
<body>
  <h1 data-testid="heading">Refresh Recovery</h1>
  <button type="button" data-testid="flaky-button">Try action</button>
  <p data-testid="status">Waiting</p>
  <script>
    const status = document.querySelector("[data-testid='status']");
    const count = Number(localStorage.getItem("refresh_recovery_count") || "0");
    if (count >= 2) {
      status.textContent = "Recovered";
    }
    document.querySelector("[data-testid='flaky-button']").addEventListener("click", () => {
      const next = Number(localStorage.getItem("refresh_recovery_count") || "0") + 1;
      localStorage.setItem("refresh_recovery_count", String(next));
      status.textContent = next >= 2 ? "Recovered" : "Waiting";
    });
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )
    return page


@pytest.mark.asyncio
async def test_local_browser_form_actions_and_success_checks(tmp_path, monkeypatch):
    pytest.importorskip("playwright.async_api")
    monkeypatch.setenv("CAPABILITY_FORM_PASSWORD", "browser-secret-fixture")
    page = _local_form_page(tmp_path)
    page_url = page.as_uri()
    workflow = {
        "id": "local_browser_form_capability",
        "name": "Local Browser Form Capability",
        "version": "1.0",
        "type": "browser",
        "inputs": {"target_url": page_url},
        "credentials": {"form_password": "CAPABILITY_FORM_PASSWORD"},
        "steps": [
            {
                "id": "open_form",
                "action": {"type": "browser.goto", "url": "${inputs.target_url}"},
                "success_check": [
                    {"type": "url_contains", "value": "local_browser_form.html"},
                    {"type": "url_equals", "value": page_url},
                    {"type": "selector_visible", "selector": {"strategy": "data-testid", "value": "heading"}},
                ],
            },
            {
                "id": "read_title",
                "action": {"type": "browser.get_title", "output": "page_title"},
                "success_check": [
                    {
                        "type": "variable_equals",
                        "value": {"var": "page_title", "value": "Capability Fixture"},
                    }
                ],
            },
            {
                "id": "read_heading",
                "action": {
                    "type": "browser.get_text",
                    "selector": {"strategy": "data-testid", "value": "heading"},
                    "output": "heading_text",
                },
                "success_check": [
                    {"type": "variable_has_value", "value": "heading_text"},
                    {
                        "type": "variable_equals",
                        "value": {"var": "heading_text", "value": "Capability Form"},
                    },
                ],
            },
            {
                "id": "fill_name",
                "action": {
                    "type": "browser.fill",
                    "selector": {"strategy": "label", "value": "Name"},
                    "value": "Rau",
                },
                "success_check": [
                    {
                        "type": "field_has_value",
                        "selector": {"strategy": "label", "value": "Name"},
                    }
                ],
            },
            {
                "id": "press_enter",
                "action": {
                    "type": "browser.press",
                    "selector": {"strategy": "label", "value": "Name"},
                    "key": "Enter",
                },
                "success_check": [
                    {
                        "type": "selector_visible",
                        "selector": {"strategy": "data-testid", "value": "press-marker"},
                    }
                ],
            },
            {
                "id": "fill_password",
                "action": {
                    "type": "browser.fill",
                    "selector": {"strategy": "label", "value": "Password"},
                    "value": "${secrets.form_password}",
                },
                "success_check": [
                    {
                        "type": "field_has_value",
                        "selector": {"strategy": "label", "value": "Password"},
                        "redacted": True,
                    }
                ],
            },
            {
                "id": "select_plan",
                "action": {
                    "type": "browser.select_option",
                    "selector": {"strategy": "label", "value": "Plan"},
                    "value": "pro",
                },
                "success_check": [
                    {
                        "type": "field_has_value",
                        "selector": {"strategy": "label", "value": "Plan"},
                    }
                ],
            },
            {
                "id": "check_advanced",
                "action": {"type": "browser.check", "selector": {"strategy": "id", "value": "toggle"}},
                "success_check": [
                    {
                        "type": "selector_visible",
                        "selector": {"strategy": "data-testid", "value": "advanced-panel"},
                    }
                ],
            },
            {
                "id": "uncheck_advanced",
                "action": {"type": "browser.uncheck", "selector": {"strategy": "id", "value": "toggle"}},
                "success_check": [
                    {
                        "type": "selector_hidden",
                        "selector": {"strategy": "data-testid", "value": "advanced-panel"},
                    }
                ],
            },
            {
                "id": "submit_form",
                "action": {
                    "type": "browser.click",
                    "selector": {"strategy": "role", "role": "button", "name": "Save"},
                },
                "success_check": [
                    {"type": "visible_text", "value": "Saved"},
                    {"type": "url_contains", "value": "#submitted"},
                ],
            },
            {
                "id": "wait_for_submitted_url",
                "action": {"type": "browser.wait_for_url", "url": f"{page_url}#submitted"},
                "success_check": [{"type": "url_equals", "value": f"{page_url}#submitted"}],
            },
            {
                "id": "wait_for_success",
                "action": {
                    "type": "browser.wait_for",
                    "selector": {"strategy": "data-testid", "value": "success"},
                    "state": "visible",
                },
                "success_check": [{"type": "visible_text", "value": "Saved"}],
            },
        ],
    }
    runner = YamlWorkflowRunner(HarnessConfig(headless=True, enable_vision=False))
    runner.failure = FailureReport(str(tmp_path / "runs"))

    result = await runner.run(str(_write_workflow(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert result["steps_completed"] == len(workflow["steps"])
    assert "browser-secret-fixture" not in json.dumps(result, default=str)


@pytest.mark.asyncio
async def test_mixed_browser_and_api_workflow_executes_end_to_end(tmp_path):
    pytest.importorskip("playwright.async_api")
    page = _local_form_page(tmp_path)

    class FakeResponse:
        status_code = 200
        text = '{"ok": true, "source": "fake-api"}'
        url = "http://127.0.0.1:8765/status?token=redacted"
        headers = {"content-type": "application/json"}

        def json(self):
            return json.loads(self.text)

    class FakeAPIDriver:
        def __init__(self):
            self.calls = []

        async def get(self, path, params=None, headers=None):
            self.calls.append({"method": "GET", "path": path, "params": params, "headers": headers})
            return FakeResponse()

        async def close(self):
            return None

    fake_api = FakeAPIDriver()
    workflow = {
        "id": "mixed_browser_api_capability",
        "name": "Mixed Browser API Capability",
        "version": "1.0",
        "type": "mixed",
        "inputs": {"target_url": page.as_uri()},
        "steps": [
            {
                "id": "open_fixture",
                "action": {"type": "browser.goto", "url": "${inputs.target_url}"},
                "success_check": [
                    {
                        "type": "selector_visible",
                        "selector": {"strategy": "data-testid", "value": "heading"},
                    }
                ],
            },
            {
                "id": "read_api_status",
                "action": {"type": "api.get", "url": "http://127.0.0.1:8765/status"},
                "success_check": [
                    {"type": "status_code", "value": 200},
                    {
                        "type": "json_path_equals",
                        "value": {"path": "$.source", "value": "fake-api"},
                    },
                ],
            },
        ],
    }
    runner = YamlWorkflowRunner(HarnessConfig(headless=True, enable_vision=False))
    runner.failure = FailureReport(str(tmp_path / "runs"))

    async def get_fake_api():
        runner._drivers["api"] = fake_api
        return fake_api

    runner._get_api_driver = get_fake_api

    result = await runner.run(str(_write_workflow(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert fake_api.calls == [
        {
            "method": "GET",
            "path": "http://127.0.0.1:8765/status",
            "params": None,
            "headers": None,
        }
    ]


@pytest.mark.asyncio
async def test_broken_selector_failure_report_includes_browser_evidence(tmp_path, monkeypatch):
    pytest.importorskip("playwright.async_api")
    monkeypatch.setenv("CAPABILITY_FORM_PASSWORD", "browser-secret-fixture")
    page = _local_form_page(tmp_path)
    workflow = {
        "id": "local_browser_failure_capability",
        "name": "Local Browser Failure Capability",
        "version": "1.0",
        "type": "browser",
        "inputs": {"target_url": page.as_uri()},
        "credentials": {"form_password": "CAPABILITY_FORM_PASSWORD"},
        "steps": [
            {
                "id": "open_form",
                "action": {"type": "browser.goto", "url": "${inputs.target_url}"},
                "success_check": [{"type": "selector_visible", "selector": {"strategy": "data-testid", "value": "heading"}}],
            },
            {
                "id": "fill_password",
                "action": {
                    "type": "browser.fill",
                    "selector": {"strategy": "label", "value": "Password"},
                    "value": "${secrets.form_password}",
                },
                "success_check": [
                    {
                        "type": "field_has_value",
                        "selector": {"strategy": "label", "value": "Password"},
                        "redacted": True,
                    }
                ],
            },
            {
                "id": "broken_click",
                "action": {
                    "type": "browser.click",
                    "selector": {"strategy": "data-testid", "value": "missing-button"},
                    "timeout": 100,
                },
                "success_check": [{"type": "visible_text", "value": "Saved"}],
            },
        ],
    }
    runner = YamlWorkflowRunner(HarnessConfig(headless=True, enable_vision=False))
    runner.failure = FailureReport(str(tmp_path / "runs"))

    result = await runner.run(str(_write_workflow(tmp_path, workflow)))

    report_path = Path(result["failure_report"])
    report = json.loads(report_path.read_text())
    assert result["status"] == "failed"
    assert report["failed_step_id"] == "broken_click"
    assert {"screenshot", "dom_snapshot", "current_url"}.issubset(report["evidence"])
    assert (report_path.parent / report["evidence"]["screenshot"]).exists()
    assert (report_path.parent / report["evidence"]["dom_snapshot"]).exists()
    assert "browser-secret-fixture" not in report_path.read_text()


@pytest.mark.asyncio
async def test_refresh_page_recovery_reloads_and_retries_browser_action(tmp_path):
    pytest.importorskip("playwright.async_api")
    page = _refresh_recovery_page(tmp_path)
    workflow = {
        "id": "local_browser_refresh_recovery",
        "name": "Local Browser Refresh Recovery",
        "version": "1.0",
        "type": "browser",
        "inputs": {"target_url": page.as_uri()},
        "steps": [
            {
                "id": "open_fixture",
                "action": {"type": "browser.goto", "url": "${inputs.target_url}"},
                "success_check": [
                    {
                        "type": "selector_visible",
                        "selector": {"strategy": "data-testid", "value": "heading"},
                    }
                ],
            },
            {
                "id": "recover_after_refresh",
                "action": {
                    "type": "browser.click",
                    "selector": {"strategy": "data-testid", "value": "flaky-button"},
                },
                "success_check": [{"type": "visible_text", "value": "Recovered"}],
                "recovery": [{"type": "refresh_page"}],
            },
        ],
    }
    runner = YamlWorkflowRunner(HarnessConfig(headless=True, enable_vision=False))
    runner.failure = FailureReport(str(tmp_path / "runs"))

    result = await runner.run(str(_write_workflow(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert result["steps"][1]["attempts"] == 2
