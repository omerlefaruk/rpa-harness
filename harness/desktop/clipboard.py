"""Safe clipboard paste helper for desktop automation."""

from __future__ import annotations

import sys
from typing import Callable, Protocol


class Clipboard(Protocol):
    def get_text(self) -> str:
        ...

    def set_text(self, value: str) -> None:
        ...


class WindowsClipboard:
    def __init__(self):
        if not sys.platform.startswith("win"):
            raise RuntimeError("Windows clipboard requires Windows")
        try:
            import win32clipboard
            import win32con
        except ImportError as exc:
            raise RuntimeError("Windows clipboard requires pywin32") from exc
        self._clipboard = win32clipboard
        self._con = win32con

    def get_text(self) -> str:
        self._clipboard.OpenClipboard()
        try:
            if not self._clipboard.IsClipboardFormatAvailable(self._con.CF_UNICODETEXT):
                return ""
            return str(self._clipboard.GetClipboardData(self._con.CF_UNICODETEXT))
        finally:
            self._clipboard.CloseClipboard()

    def set_text(self, value: str) -> None:
        self._clipboard.OpenClipboard()
        try:
            self._clipboard.EmptyClipboard()
            self._clipboard.SetClipboardData(self._con.CF_UNICODETEXT, str(value))
        finally:
            self._clipboard.CloseClipboard()


def _send_ctrl_v(_: str = "ctrl+v") -> None:
    try:
        import pyautogui

        pyautogui.hotkey("ctrl", "v")
        return
    except ImportError:
        pass
    try:
        from pywinauto.keyboard import send_keys

        send_keys("^v")
        return
    except ImportError as exc:
        raise RuntimeError("Clipboard paste requires pyautogui or pywinauto") from exc


class ClipboardPaste:
    def __init__(
        self,
        clipboard: Clipboard | None = None,
        send_hotkey: Callable[[str], None] | None = None,
    ):
        self.clipboard = clipboard or WindowsClipboard()
        self.send_hotkey = send_hotkey or _send_ctrl_v

    def paste_text(self, value: str) -> None:
        previous = self.clipboard.get_text()
        try:
            self.clipboard.set_text(value)
            self.send_hotkey("ctrl+v")
        finally:
            self.clipboard.set_text(previous)
