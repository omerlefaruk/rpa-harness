import os
import sys

import pytest

from harness.config import HarnessConfig

pytestmark = pytest.mark.skipif(
    os.getenv("RPA_RUN_WINDOWS_DESKTOP_SMOKE") != "1",
    reason="Set RPA_RUN_WINDOWS_DESKTOP_SMOKE=1 to launch real Windows desktop apps.",
)


def _windows_only():
    if not sys.platform.startswith("win"):
        pytest.skip("Windows desktop smoke tests require Windows")


@pytest.mark.asyncio
async def test_windows_uia_notepad_smoke(tmp_path):
    _windows_only()
    pytest.importorskip("pywinauto")
    from harness.drivers.windows_ui import WindowsUIDriver

    app = os.getenv("RPA_WINDOWS_SMOKE_APP", "notepad.exe")
    title = os.getenv("RPA_WINDOWS_SMOKE_TITLE", "Notepad")
    class_name = os.getenv("RPA_WINDOWS_SMOKE_CLASS")
    driver = WindowsUIDriver(HarnessConfig(report_dir=str(tmp_path)))
    try:
        await driver.launch_app(app, app_name="desktop-smoke", wait_for_window=False)
        await driver.connect_to_app(title=title, class_name=class_name, timeout=10)
        tree = await driver.dump_tree(max_depth=1)
        screenshot = await driver.screenshot("uia_smoke.png")

        assert tree
        assert (tmp_path / "uia_smoke.png").exists()
        assert screenshot.endswith("uia_smoke.png")
    finally:
        await driver.close()


@pytest.mark.asyncio
async def test_windows_win32_notepad_smoke(tmp_path):
    _windows_only()
    pytest.importorskip("win32gui")
    from harness.drivers.win32_ui import Win32UIDriver

    app = os.getenv("RPA_WINDOWS_SMOKE_APP", "notepad.exe")
    title = os.getenv("RPA_WINDOWS_SMOKE_TITLE", "Notepad")
    class_name = os.getenv("RPA_WINDOWS_SMOKE_CLASS")
    driver = Win32UIDriver(HarnessConfig(report_dir=str(tmp_path)))
    try:
        await driver.launch_app(app, app_name="desktop-smoke", wait_for_window=False)
        await driver.connect_to_app(title=title, class_name=class_name, timeout=10)
        tree = await driver.dump_tree(max_depth=1)
        rect = await driver.window_rect()
        screenshot = await driver.screenshot("win32_smoke.png")

        assert tree
        assert rect[2] > 0 and rect[3] > 0
        assert (tmp_path / "win32_smoke.png").exists()
        assert screenshot.endswith("win32_smoke.png")
    finally:
        await driver.close()
