import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from harness.dsl import compile_dsl_to_workflow, parse_dsl
from harness.rpa.schema import validate_workflow_schema


VALID_DSL = """*** Settings ***
Name    Download Invoice
Tag     invoices

*** Variables ***
${portal_url}    https://vendor.example.com/login
${download_path}    downloads/latest-invoice.pdf

*** Tasks ***
Download Invoice
    Open Browser    ${portal_url}
    Verify Url Contains    /login
    Verify File Exists    ${download_path}
"""


def test_parse_task_variables_and_steps():
    parsed = parse_dsl(VALID_DSL)

    assert parsed.name == "Download Invoice"
    assert parsed.tags == ["invoices"]
    assert parsed.variables == {
        "portal_url": "https://vendor.example.com/login",
        "download_path": "downloads/latest-invoice.pdf",
    }
    assert parsed.tasks[0].name == "Download Invoice"
    assert parsed.tasks[0].steps[0].keyword == "Open Browser"
    assert parsed.tasks[0].steps[0].args == ["${portal_url}"]


def test_compile_open_browser_to_schema_v2_workflow():
    workflow = compile_dsl_to_workflow(parse_dsl(VALID_DSL))

    assert workflow["schema_version"] == 2
    assert workflow["id"] == "download_invoice"
    assert workflow["metadata"]["tags"] == ["invoices"]
    assert workflow["policies"]["require_success_checks"] is True
    first_step = workflow["phases"][0]["steps"][0]
    assert first_step["action"]["type"] == "browser.goto"
    assert first_step["action"]["url"] == "https://vendor.example.com/login"
    assert first_step["success_checks"] == [{"type": "url_contains", "value": "/login"}]
    assert validate_workflow_schema(workflow)["errors"] == []


def test_unknown_keyword_fails_closed():
    source = """*** Tasks ***
Download Invoice
    Guess The Best Selector
"""

    with pytest.raises(ValueError, match="Unknown DSL keyword"):
        compile_dsl_to_workflow(parse_dsl(source))


def test_action_step_requires_following_verification():
    source = """*** Variables ***
${portal_url}    https://vendor.example.com/login

*** Tasks ***
Download Invoice
    Open Browser    ${portal_url}
"""

    with pytest.raises(ValueError, match="Open Browser must be followed by a verification"):
        compile_dsl_to_workflow(parse_dsl(source))


def test_compile_dsl_cli_writes_yaml(tmp_path):
    source = tmp_path / "download_invoice.rpa"
    output = tmp_path / "download_invoice.yaml"
    source.write_text(VALID_DSL, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--compile-dsl",
            str(source),
            "--workflow-output",
            str(output),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    workflow = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert workflow["schema_version"] == 2
    assert workflow["id"] == "download_invoice"
