"""Minimal Win32 desktop fallback driver."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from harness.config import HarnessConfig
from harness.drivers.base import AbstractBaseDriver
from harness.drivers.windows_ui import UIElement


class Win32UIDriver(AbstractBaseDriver):
    driver_type = "win32_ui"

    def __init__(self, config: Optional[HarnessConfig] = None):
        super().__init__(config)
        self._process = None
        self._window: int | None = None
        self._win32gui = None
        self._win32con = None
        self._win32api = None
        if sys.platform.startswith("win"):
            try:
                import win32api
                import win32con
                import win32gui

                self._win32api = win32api
                self._win32con = win32con
                self._win32gui = win32gui
            except ImportError:
                self.logger.warning("pywin32 not installed. Win32 automation unavailable.")

    async def launch(self, **kwargs):
        return await self.launch_app(**kwargs)

    async def launch_app(
        self,
        app_path: str,
        app_name: str | None = None,
        wait_for_window: bool = True,
        timeout: int = 30,
    ):
        if not self._win32gui:
            raise RuntimeError("pywin32 not available")
        self._process = subprocess.Popen(app_path, shell=True)
        if wait_for_window:
            await asyncio.sleep(min(timeout, 2))
        self._connected = True

    async def connect_to_app(
        self,
        title: str | None = None,
        class_name: str | None = None,
        timeout: int = 10,
    ):
        if not self._win32gui:
            raise RuntimeError("pywin32 not available")
        deadline = time.time() + timeout
        while time.time() < deadline:
            hwnd = self._find_window(title=title, class_name=class_name)
            if hwnd:
                self._window = hwnd
                self._connected = True
                return
            await asyncio.sleep(0.2)
        raise RuntimeError(f"Win32 window not found: title={title!r} class_name={class_name!r}")

    async def find_element(
        self,
        name: str | None = None,
        class_name: str | None = None,
        control_type: str | None = None,
        control_id: str | int | None = None,
        hwnd: str | int | None = None,
        timeout: int = 10,
        **_: Any,
    ) -> UIElement | None:
        if not self._window and hwnd is None:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self._find_child(
                name=name,
                class_name=class_name or control_type,
                control_id=control_id,
                hwnd=hwnd,
            )
            if found:
                return self._element(found)
            await asyncio.sleep(0.2)
        return None

    async def click(self, timeout: int = 10, **selector: Any):
        element = await self.find_element(timeout=timeout, **selector)
        if not element or not element.native_element:
            raise RuntimeError(f"Win32 element not found: {selector}")
        hwnd = int(element.native_element)
        if self._win32gui.GetClassName(hwnd).lower() == "button":
            await asyncio.to_thread(
                self._win32gui.SendMessage,
                hwnd,
                self._win32con.BM_CLICK,
                0,
                0,
            )
            return
        if not getattr(self.config, "allow_coordinate_fallback", False):
            raise RuntimeError("Win32 coordinate click requires allow_coordinate_fallback=True")
        left, top, right, bottom = self._win32gui.GetWindowRect(hwnd)
        await asyncio.to_thread(self._win32api.SetCursorPos, ((left + right) // 2, (top + bottom) // 2))
        await asyncio.to_thread(self._win32api.mouse_event, self._win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        await asyncio.to_thread(self._win32api.mouse_event, self._win32con.MOUSEEVENTF_LEFTUP, 0, 0)

    async def get_text(self, timeout: int = 10, **selector: Any) -> str | None:
        element = await self.find_element(timeout=timeout, **selector)
        if not element or not element.native_element:
            return None
        return str(self._win32gui.GetWindowText(int(element.native_element)))

    async def type_keys(self, text: str, timeout: int = 10, **selector: Any):
        raise RuntimeError("Win32 type_keys is not supported; use desktop.clipboard_paste")

    async def press_keys(self, keys: str):
        raise RuntimeError("Win32 press_keys is not supported")

    async def menu_select(self, path: str):
        raise RuntimeError("Win32 menu_select is not supported for this target")

    async def dump_tree(self, max_depth: int = 3) -> dict[str, Any]:
        if not self._window:
            return {}
        return self._dump(self._window, depth=0, max_depth=max_depth)

    async def screenshot(self, name: Optional[str] = None) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = name or f"desktop_win32_{ts}.png"
        report_dir = self.config.report_dir if self.config else "./reports"
        path = Path(report_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import ImageGrab

        ImageGrab.grab().save(str(path))
        self._screenshots.append(str(path))
        return str(path)

    async def close_app(self):
        self._connected = False
        if self._process:
            self._process.terminate()

    async def close(self):
        await self.close_app()

    async def window_rect(self) -> tuple[int, int, int, int]:
        if not self._window:
            raise RuntimeError("window_rect requires an attached window")
        left, top, right, bottom = self._win32gui.GetWindowRect(self._window)
        return left, top, right - left, bottom - top

    def _find_window(self, *, title: str | None = None, class_name: str | None = None) -> int | None:
        title_lc = (title or "").lower()
        windows: list[int] = []

        def callback(hwnd, _):
            try:
                if self._win32gui.IsWindowVisible(hwnd):
                    windows.append(int(hwnd))
            except Exception:
                pass
            return True

        self._win32gui.EnumWindows(callback, None)
        for hwnd in windows:
            window_title = str(self._win32gui.GetWindowText(hwnd))
            window_class = str(self._win32gui.GetClassName(hwnd))
            if title_lc and title_lc not in window_title.lower():
                continue
            if class_name and class_name != window_class:
                continue
            return hwnd
        return None

    def _find_child(
        self,
        *,
        name: str | None = None,
        class_name: str | None = None,
        control_id: str | int | None = None,
        hwnd: str | int | None = None,
    ) -> int | None:
        if hwnd is not None:
            return int(hwnd)
        children: list[int] = []

        def callback(child_hwnd, _):
            children.append(int(child_hwnd))
            return True

        self._win32gui.EnumChildWindows(self._window, callback, None)
        for child in children:
            if name and name != str(self._win32gui.GetWindowText(child)):
                continue
            if class_name and class_name != str(self._win32gui.GetClassName(child)):
                continue
            if control_id is not None and str(control_id) != str(self._win32gui.GetDlgCtrlID(child)):
                continue
            return child
        return None

    def _element(self, hwnd: int) -> UIElement:
        left, top, right, bottom = self._win32gui.GetWindowRect(hwnd)
        return UIElement(
            name=str(self._win32gui.GetWindowText(hwnd)),
            automation_id=str(self._win32gui.GetDlgCtrlID(hwnd)),
            class_name=str(self._win32gui.GetClassName(hwnd)),
            control_type=str(self._win32gui.GetClassName(hwnd)),
            rect=(left, top, right - left, bottom - top),
            native_element=hwnd,
        )

    def _dump(self, hwnd: int, *, depth: int, max_depth: int) -> dict[str, Any]:
        element = self._element(hwnd).to_dict()
        element["hwnd"] = hwnd
        if depth >= max_depth:
            element["_truncated"] = True
            element["children"] = []
            return element
        children: list[int] = []

        def callback(child_hwnd, _):
            children.append(int(child_hwnd))
            return True

        self._win32gui.EnumChildWindows(hwnd, callback, None)
        element["children"] = [
            self._dump(child, depth=depth + 1, max_depth=max_depth) for child in children[:100]
        ]
        return element
