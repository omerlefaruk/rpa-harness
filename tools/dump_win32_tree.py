#!/usr/bin/env python3
"""Dump a Windows Win32 window/control tree as JSON."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


def element_payload(hwnd: int, win32gui: Any) -> dict[str, Any]:
    try:
        rect = list(win32gui.GetWindowRect(hwnd))
    except Exception:
        rect = None
    try:
        control_id = int(win32gui.GetDlgCtrlID(hwnd))
    except Exception:
        control_id = 0
    return {
        "hwnd": int(hwnd),
        "text": str(win32gui.GetWindowText(hwnd)),
        "class_name": str(win32gui.GetClassName(hwnd)),
        "control_id": control_id,
        "rect": rect,
    }


def _enum_children(hwnd: int, win32gui: Any) -> list[int]:
    children: list[int] = []

    def callback(child_hwnd, _):
        children.append(int(child_hwnd))
        return True

    win32gui.EnumChildWindows(hwnd, callback, None)
    return children


def _dump(hwnd: int, win32gui: Any, *, depth: int = 0, max_depth: int = 3) -> dict[str, Any]:
    payload = element_payload(hwnd, win32gui)
    if depth >= max_depth:
        payload["_truncated"] = True
        payload["children"] = []
        return payload
    payload["children"] = [
        _dump(child, win32gui, depth=depth + 1, max_depth=max_depth)
        for child in _enum_children(hwnd, win32gui)[:100]
    ]
    return payload


def _visible_top_windows(win32gui: Any) -> list[int]:
    windows: list[int] = []

    def callback(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                windows.append(int(hwnd))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def find_window(win32gui: Any, *, title: str | None = None, class_name: str | None = None) -> int | None:
    deadline = time.time() + 10
    title_lc = (title or "").lower()
    while time.time() < deadline:
        for hwnd in _visible_top_windows(win32gui):
            window_title = str(win32gui.GetWindowText(hwnd))
            window_class = str(win32gui.GetClassName(hwnd))
            if title_lc and title_lc not in window_title.lower():
                continue
            if class_name and class_name != window_class:
                continue
            return hwnd
        time.sleep(0.2)
    return None


def dump_win32_tree(*, window_title: str | None = None, class_name: str | None = None, max_depth: int = 3) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"status": "skipped", "reason": "Windows only - pywin32 required"}
    try:
        import win32gui
    except ImportError:
        return {"status": "error", "reason": "pywin32 not installed"}

    hwnd = find_window(win32gui, title=window_title, class_name=class_name)
    if not hwnd:
        return {"status": "error", "reason": "No window found"}

    tree = _dump(hwnd, win32gui, max_depth=max_depth)
    return {
        "status": "ok",
        "backend": "win32",
        "window": {
            "hwnd": hwnd,
            "title": tree["text"],
            "class_name": tree["class_name"],
        },
        "tree": tree,
        "elements": tree.get("children", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump Win32 window/control tree")
    parser.add_argument("--window-title", help="Window title substring")
    parser.add_argument("--class-name", help="Exact top-level window class name")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--output", "-o")
    args = parser.parse_args()

    result = dump_win32_tree(
        window_title=args.window_title,
        class_name=args.class_name,
        max_depth=args.max_depth,
    )
    text = json.dumps(result, indent=2, default=str)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
