"""Capability characterization for YAML Excel runtime and desktop runtime boundary."""

from pathlib import Path

import pytest
import yaml

from harness.config import HarnessConfig
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
    assert result["failure_type"] == "preflight"
    assert any("input file does not exist" in error for error in result["preflight"]["blocking_errors"])


class FakeDesktopElement:
    def __init__(self, selector=None):
        self.selector = selector or {}

    def to_dict(self):
        data = dict(self.selector)
        data.setdefault("automation_id", "Submit")
        data.setdefault("name", "Submit")
        return data


class FakeDesktopDriver:
    driver_type = "fake_desktop"

    def __init__(self, screenshot_path: Path):
        self.screenshot_path = screenshot_path
        self.calls = []

    async def launch_app(self, **kwargs):
        self.calls.append(("launch_app", kwargs))

    async def connect_to_app(self, **kwargs):
        self.calls.append(("connect_to_app", kwargs))

    async def find_element(self, **kwargs):
        self.calls.append(("find_element", kwargs))
        return FakeDesktopElement(kwargs)

    async def click(self, **kwargs):
        self.calls.append(("click", kwargs))

    async def get_text(self, **kwargs):
        self.calls.append(("get_text", kwargs))
        return "Ready"

    async def type_keys(self, **kwargs):
        self.calls.append(("type_keys", kwargs))

    async def press_keys(self, keys):
        self.calls.append(("press_keys", keys))

    async def menu_select(self, path):
        self.calls.append(("menu_select", path))

    async def dump_tree(self, max_depth=3):
        self.calls.append(("dump_tree", max_depth))
        return {"name": "Root", "children": [{"name": "Ready"}]}

    async def screenshot(self, name=None):
        self.screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.screenshot_path.write_bytes(b"fake")
        self.calls.append(("screenshot", name))
        return str(self.screenshot_path)

    async def window_rect(self):
        return (10, 20, 100, 200)

    async def close_app(self):
        self.calls.append(("close_app", {}))


@pytest.mark.asyncio
async def test_desktop_yaml_extended_uia_actions_use_driver(tmp_path):
    screenshot = tmp_path / "desktop.png"
    workflow = {
        "id": "desktop_extended_actions",
        "name": "Desktop Extended Actions",
        "version": "1.0",
        "type": "desktop",
        "steps": [
            {
                "id": "attach",
                "action": {"type": "desktop.attach", "window_title": "Legacy ERP"},
                "success_check": [{"type": "window_exists", "value": "Legacy ERP"}],
            },
            {
                "id": "type_text",
                "action": {
                    "type": "desktop.type",
                    "selector": {"strategy": "automation_id", "value": "notes"},
                    "text": "hello",
                },
                "success_check": [{"type": "field_has_value"}],
            },
            {
                "id": "press_keys",
                "action": {"type": "desktop.press", "keys": "ctrl+s"},
                "success_check": [{"type": "variable_has_value", "value": "keys_pressed"}],
            },
            {
                "id": "menu",
                "action": {"type": "desktop.menu_select", "path": "File->Save"},
                "success_check": [{"type": "variable_has_value", "value": "menu_path"}],
            },
            {
                "id": "wait_element",
                "action": {
                    "type": "desktop.wait",
                    "selector": {"strategy": "automation_id", "value": "Submit"},
                },
                "success_check": [
                    {
                        "type": "element_exists",
                        "selector": {"strategy": "automation_id", "value": "Submit"},
                    }
                ],
            },
            {
                "id": "read_text",
                "action": {
                    "type": "desktop.get_text",
                    "selector": {"strategy": "automation_id", "value": "status"},
                    "output": "status_text",
                },
                "success_check": [{"type": "text_contains", "value": "Ready"}],
            },
            {
                "id": "shot",
                "action": {"type": "desktop.screenshot", "name": "desktop.png"},
                "success_check": [{"type": "file_exists", "value": str(screenshot)}],
            },
            {
                "id": "tree",
                "action": {"type": "desktop.dump_tree", "output": "tree"},
                "success_check": [{"type": "variable_has_value", "value": "tree"}],
            },
        ],
    }
    runner = YamlWorkflowRunner()
    fake = FakeDesktopDriver(screenshot)
    runner._drivers["desktop"] = fake

    result = await runner.run(str(_write_yaml(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert result["steps_completed"] == 8
    assert ("menu_select", "File->Save") in fake.calls


@pytest.mark.asyncio
async def test_desktop_yaml_win32_backend_uses_win32_driver(tmp_path):
    workflow = {
        "id": "desktop_win32_backend",
        "name": "Desktop Win32 Backend",
        "version": "1.0",
        "type": "desktop",
        "steps": [
            {
                "id": "click_win32",
                "action": {
                    "type": "desktop.click",
                    "selector": {
                        "backend": "win32",
                        "strategy": "win32_control_id",
                        "value": "15",
                    },
                },
                "success_check": [{"type": "element_exists"}],
            }
        ],
    }
    runner = YamlWorkflowRunner()
    fake = FakeDesktopDriver(tmp_path / "desktop.png")
    runner._drivers["desktop:win32"] = fake

    result = await runner.run(str(_write_yaml(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert ("click", {"timeout": 10, "control_id": "15"}) in fake.calls


@pytest.mark.asyncio
async def test_coordinate_desktop_selector_requires_explicit_config(tmp_path):
    runner = YamlWorkflowRunner()
    runner._drivers["desktop"] = FakeDesktopDriver(tmp_path / "desktop.png")

    with pytest.raises(RuntimeError, match="allow_coordinate_fallback"):
        await runner._execute_desktop_action(
            "desktop.click",
            {
                "selector": {
                    "strategy": "coordinate",
                    "value": {"x_ratio": 0.5, "y_ratio": 0.5},
                }
            },
        )


@pytest.mark.asyncio
async def test_coordinate_desktop_selector_uses_window_relative_ratios(tmp_path):
    runner = YamlWorkflowRunner(HarnessConfig(allow_coordinate_fallback=True))
    fake = FakeDesktopDriver(tmp_path / "desktop.png")
    runner._drivers["desktop"] = fake

    result = await runner._execute_desktop_action(
        "desktop.click",
        {
            "selector": {
                "strategy": "coordinate",
                "value": {"x_ratio": 0.5, "y_ratio": 0.25},
            }
        },
    )

    assert result["selector_quality"] == "coordinate_fallback"
    assert ("click", {"timeout": 10, "coordinates": (60, 70)}) in fake.calls
