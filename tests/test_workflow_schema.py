"""Tests for YAML workflow validation and execution."""
import pytest
from pathlib import Path

from harness.verification import validate_workflow
from harness.rpa.yaml_runner import YamlWorkflowRunner


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
        "name": "Bad", "version": "1.0", "type": "browser",
        "steps": [{
            "id": "s1",
            "action": {"type": "browser.click"},
        }],
    }
    errors = validate_workflow(wf)
    assert len(errors) == 1
    assert "missing success_check" in errors[0]


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
async def test_yaml_runner_run():
    wf_path = Path(__file__).parent.parent / "workflows" / "examples" / "minimal_example.yaml"
    if not wf_path.exists():
        pytest.skip("minimal_example.yaml not found")
    runner = YamlWorkflowRunner()
    result = await runner.run(str(wf_path))
    assert result["status"] == "passed"
    assert result["steps_completed"] > 0
