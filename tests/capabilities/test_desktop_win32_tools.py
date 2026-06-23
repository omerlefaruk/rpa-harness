import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_dump_tool():
    path = Path(__file__).parents[2] / "tools" / "dump_win32_tree.py"
    spec = importlib.util.spec_from_file_location("dump_win32_tree", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeWin32Driver:
    def __init__(self):
        self._win32gui = object()
        self.connected = None
        self.closed = False

    async def connect_to_app(self, *, title=None, class_name=None, timeout=10):
        self.connected = {"title": title, "class_name": class_name, "timeout": timeout}

    async def dump_tree(self, max_depth=3):
        return {
            "hwnd": 100,
            "name": "Untitled - Notepad",
            "class_name": "Notepad",
            "children": [
                {
                    "hwnd": 101,
                    "name": "Edit",
                    "class_name": "Edit",
                    "automation_id": "15",
                    "rect": (10, 20, 200, 100),
                }
            ],
        }

    async def close(self):
        self.closed = True


def test_dump_win32_tree_uses_driver_dump(monkeypatch):
    tool = _load_dump_tool()
    monkeypatch.setattr(tool.sys, "platform", "win32")
    monkeypatch.setattr(tool, "Win32UIDriver", FakeWin32Driver)

    result = tool.dump_win32_tree(window_title="Notepad", class_name="Notepad", max_depth=2)

    assert result["status"] == "ok"
    assert result["backend"] == "win32"
    assert result["window"] == {
        "hwnd": 100,
        "title": "Untitled - Notepad",
        "class_name": "Notepad",
    }
    assert result["elements"][0]["automation_id"] == "15"


def test_dump_win32_tree_skips_non_windows(monkeypatch):
    tool = _load_dump_tool()
    monkeypatch.setattr(tool.sys, "platform", "linux")

    result = tool.dump_win32_tree()

    assert result == {"status": "skipped", "reason": "Windows only - pywin32 required"}


def test_dump_win32_tree_script_help_runs_from_repo_root():
    repo = Path(__file__).parents[2]

    completed = subprocess.run(
        [sys.executable, "-I", "tools/dump_win32_tree.py", "--help"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Dump Win32 window/control tree" in completed.stdout
