"""Capability characterization for YAML Excel runtime and desktop runtime boundary."""

from pathlib import Path

import pytest
import yaml

from harness.rpa.yaml_runner import YamlWorkflowRunner


def _write_yaml(tmp_path: Path, workflow: dict) -> Path:
    path = tmp_path / f"{workflow['id']}.yaml"
    path.write_text(yaml.safe_dump(workflow))
    return path


@pytest.mark.asyncio
async def test_excel_yaml_write_append_read_and_verify_cells(tmp_path):
    workbook = tmp_path / "capability.xlsx"
    workflow = {
        "id": "excel_runtime_capability",
        "name": "Excel Runtime Capability",
        "version": "1.0",
        "type": "excel",
        "inputs": {"workbook": str(workbook)},
        "steps": [
            {
                "id": "write_rows",
                "action": {
                    "type": "excel.write",
                    "path": "${inputs.workbook}",
                    "sheet": "Results",
                    "headers": ["ID", "Status"],
                    "rows": [["1", "OK"]],
                },
                "success_check": [
                    {"type": "workbook_exists", "value": "${inputs.workbook}"},
                    {"type": "sheet_exists", "value": "Results"},
                    {
                        "type": "cell_equals",
                        "value": {"sheet": "Results", "cell": "B2", "value": "OK"},
                    },
                ],
            },
            {
                "id": "append_row",
                "action": {
                    "type": "excel.append_row",
                    "path": "${inputs.workbook}",
                    "sheet": "Results",
                    "row_data": ["2", "DONE"],
                },
                "success_check": [
                    {
                        "type": "cell_equals",
                        "value": {"sheet": "Results", "cell": "B3", "value": "DONE"},
                    }
                ],
            },
            {
                "id": "read_rows",
                "action": {
                    "type": "excel.read",
                    "path": "${inputs.workbook}",
                    "sheet": "Results",
                    "output": "excel_rows",
                },
                "success_check": [
                    {"type": "variable_has_value", "value": "excel_rows"},
                    {
                        "type": "cell_equals",
                        "value": {"sheet": "Results", "cell": "A3", "value": "2"},
                    },
                ],
            },
        ],
    }

    result = await YamlWorkflowRunner().run(str(_write_yaml(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert result["steps_completed"] == 3


@pytest.mark.asyncio
async def test_excel_yaml_missing_input_file_fails_predictably(tmp_path):
    missing = tmp_path / "missing.xlsx"
    workflow = {
        "id": "excel_missing_input",
        "name": "Excel Missing Input",
        "version": "1.0",
        "type": "excel",
        "inputs": {"workbook": str(missing)},
        "steps": [
            {
                "id": "read_missing",
                "action": {
                    "type": "excel.read",
                    "path": "${inputs.workbook}",
                },
                "success_check": [{"type": "workbook_exists", "value": "${inputs.workbook}"}],
            }
        ],
    }

    result = await YamlWorkflowRunner().run(str(_write_yaml(tmp_path, workflow)))

    assert result["status"] == "failed"
    assert result["failure_type"] == "execution"
    assert "Workbook not found" in result["reason"]
