import sys

import pytest
import yaml

from harness.config import HarnessConfig
from harness.desktop.clipboard import ClipboardPaste
from harness.desktop.ocr import OcrEngine
from harness.rpa.yaml_runner import YamlWorkflowRunner
from tests.capabilities.test_yaml_excel_desktop_runtime import FakeDesktopDriver, _write_yaml


class FakeClipboard:
    def __init__(self, value=""):
        self.value = value

    def get_text(self):
        return self.value

    def set_text(self, value):
        self.value = value


def test_clipboard_restore_after_paste():
    clipboard = FakeClipboard("before")
    sent = []
    paste = ClipboardPaste(clipboard=clipboard, send_hotkey=sent.append)

    paste.paste_text("new value")

    assert clipboard.get_text() == "before"
    assert sent == ["ctrl+v"]


def test_clipboard_restore_after_failure():
    clipboard = FakeClipboard("before")

    def fail(_):
        raise RuntimeError("paste failed")

    paste = ClipboardPaste(clipboard=clipboard, send_hotkey=fail)

    with pytest.raises(RuntimeError, match="paste failed"):
        paste.paste_text("new value")

    assert clipboard.get_text() == "before"


def test_ocr_without_command_is_blocked(tmp_path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"fake")

    result = OcrEngine(command=None).read_image(image)

    assert result["status"] == "blocked"
    assert "OCR command is not configured" in result["reason"]


def test_ocr_command_output_is_redacted(tmp_path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"fake")

    result = OcrEngine(
        command=[sys.executable, "-c", "print('Ready token=secret-value')"]
    ).read_image(image, secret_values=["secret-value"])

    assert result["status"] == "ok"
    assert result["text"] == "Ready token=[REDACTED]"


@pytest.mark.asyncio
async def test_desktop_clipboard_paste_action_redacts_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKTOP_NOTES_SECRET", "secret-note")
    workflow = {
        "id": "desktop_clipboard_secret",
        "name": "Desktop Clipboard Secret",
        "version": "1.0",
        "type": "desktop",
        "credentials": {"notes": "DESKTOP_NOTES_SECRET"},
        "steps": [
            {
                "id": "paste_secret",
                "action": {
                    "type": "desktop.clipboard_paste",
                    "selector": {"strategy": "automation_id", "value": "notes"},
                    "secret": "notes",
                },
                "success_check": [{"type": "field_has_value", "redacted": True}],
            }
        ],
    }
    runner = YamlWorkflowRunner()
    runner._drivers["desktop"] = FakeDesktopDriver(tmp_path / "desktop.png")
    clipboard = FakeClipboard("before")
    runner._clipboard_paste_factory = lambda: ClipboardPaste(
        clipboard=clipboard,
        send_hotkey=lambda _: None,
    )

    result = await runner.run(str(_write_yaml(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert clipboard.get_text() == "before"
    assert "secret-note" not in yaml.safe_dump(result)


@pytest.mark.asyncio
async def test_desktop_ocr_read_and_wait_actions(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "RPA_OCR_COMMAND",
        f"\"{sys.executable}\" -c \"print('Ready')\"",
    )
    workflow = {
        "id": "desktop_ocr",
        "name": "Desktop OCR",
        "version": "1.0",
        "type": "desktop",
        "steps": [
            {
                "id": "read_ocr",
                "action": {
                    "type": "desktop.ocr_read",
                    "region": {"anchor": "window"},
                    "output": "ocr_text",
                },
                "success_check": [{"type": "text_contains", "value": "Ready"}],
            },
            {
                "id": "wait_ocr",
                "action": {
                    "type": "desktop.ocr_wait",
                    "text": "Ready",
                    "region": {"anchor": "window"},
                },
                "success_check": [{"type": "text_contains", "value": "Ready"}],
            },
        ],
    }
    runner = YamlWorkflowRunner(HarnessConfig())
    runner._drivers["desktop"] = FakeDesktopDriver(tmp_path / "desktop.png")

    result = await runner.run(str(_write_yaml(tmp_path, workflow)))

    assert result["status"] == "passed"
    assert result["steps_completed"] == 2
