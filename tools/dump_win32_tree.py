#!/usr/bin/env python3
"""Dump a Windows Win32 window/control tree as JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.drivers.win32_ui import Win32UIDriver


async def _dump_win32_tree(
    *,
    window_title: str | None = None,
    class_name: str | None = None,
    max_depth: int = 3,
    timeout: int = 10,
) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"status": "skipped", "reason": "Windows only - pywin32 required"}

    driver = Win32UIDriver()
    if not getattr(driver, "_win32gui", None):
        return {"status": "error", "reason": "pywin32 not installed"}

    try:
        await driver.connect_to_app(title=window_title, class_name=class_name, timeout=timeout)
        tree = await driver.dump_tree(max_depth=max_depth)
        return {
            "status": "ok",
            "backend": "win32",
            "window": {
                "hwnd": tree.get("hwnd"),
                "title": tree.get("name") or tree.get("text", ""),
                "class_name": tree.get("class_name", ""),
            },
            "tree": tree,
            "elements": tree.get("children", []),
        }
    except RuntimeError as exc:
        return {"status": "error", "reason": str(exc)}
    finally:
        await driver.close()


def dump_win32_tree(
    *,
    window_title: str | None = None,
    class_name: str | None = None,
    max_depth: int = 3,
    timeout: int = 10,
) -> dict[str, Any]:
    return asyncio.run(
        _dump_win32_tree(
            window_title=window_title,
            class_name=class_name,
            max_depth=max_depth,
            timeout=timeout,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump Win32 window/control tree")
    parser.add_argument("--window-title", help="Window title substring")
    parser.add_argument("--class-name", help="Exact top-level window class name")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--output", "-o")
    args = parser.parse_args()

    result = dump_win32_tree(
        window_title=args.window_title,
        class_name=args.class_name,
        max_depth=args.max_depth,
        timeout=args.timeout,
    )
    text = json.dumps(result, indent=2, default=str)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text)
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
