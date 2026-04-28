"""Opt-in integration tests for real YAML browser/API execution."""

import os

import pytest

from harness.config import HarnessConfig
from harness.rpa.yaml_runner import YamlWorkflowRunner

pytestmark = pytest.mark.skipif(
    os.getenv("RPA_RUN_INTEGRATION") != "1",
    reason="Set RPA_RUN_INTEGRATION=1 to run real browser/API integration tests.",
)


@pytest.mark.asyncio
async def test_real_browser_yaml_runner_with_local_page(tmp_path):
    pytest.importorskip(
        "playwright.async_api",
        reason="Playwright package is required for browser YAML integration tests.",
    )
    page = tmp_path / "index.html"
    page.write_text("<html><body><h1 data-testid='title'>Local OK</h1></body></html>")
    workflow = tmp_path / "browser.yaml"
    workflow.write_text(f"""
id: local_browser
name: Local Browser
version: "1.0"
type: browser
inputs:
  target_url: "{page.as_uri()}"
steps:
  - id: open_page
    action:
      type: browser.goto
      url: "${{inputs.target_url}}"
    success_check:
      - type: url_contains
        value: "index.html"
  - id: read_title
    action:
      type: browser.get_text
      selector:
        strategy: data-testid
        value: title
      output: page_heading
    success_check:
      - type: variable_equals
        value:
          var: page_heading
          value: "Local OK"
""")

    config = HarnessConfig(headless=True, enable_vision=False)
    result = await YamlWorkflowRunner(config).run(str(workflow))
    assert result["status"] == "passed"
