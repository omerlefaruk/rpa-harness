import importlib.util
from pathlib import Path


def _load_dump_tool():
    path = Path(__file__).parents[2] / "tools" / "dump_win32_tree.py"
    spec = importlib.util.spec_from_file_location("dump_win32_tree", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeWin32Gui:
    def GetWindowText(self, hwnd):
        return {100: "Untitled - Notepad", 101: "Edit"}.get(hwnd, "")

    def GetClassName(self, hwnd):
        return {100: "Notepad", 101: "Edit"}.get(hwnd, "")

    def GetDlgCtrlID(self, hwnd):
        return {100: 0, 101: 15}.get(hwnd, 0)

    def GetWindowRect(self, hwnd):
        return (10, 20, 210, 120)


def test_dump_win32_tree_element_payload_shape():
    tool = _load_dump_tool()

    result = tool.element_payload(101, FakeWin32Gui())

    assert result == {
        "hwnd": 101,
        "text": "Edit",
        "class_name": "Edit",
        "control_id": 15,
        "rect": [10, 20, 210, 120],
    }


def test_dump_win32_tree_output_shape():
    result = {
        "status": "ok",
        "backend": "win32",
        "window": {"title": "Untitled - Notepad", "class_name": "Notepad"},
        "elements": [element := _load_dump_tool().element_payload(101, FakeWin32Gui())],
    }

    assert result["backend"] == "win32"
    assert {"hwnd", "text", "class_name", "control_id", "rect"}.issubset(element)
