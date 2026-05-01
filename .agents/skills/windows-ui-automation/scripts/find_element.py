#!/usr/bin/env python3
"""Find a UIA element by name, automation ID, or class."""
import argparse, json, sys


def find_element(name: str = None, automation_id: str = None, class_name: str = None,
                 control_type: str = None, timeout: float = 10.0) -> dict:
    if not sys.platform.startswith("win"):
        return {"status": "skipped", "reason": "Windows only"}

    try:
        from pywinauto import Desktop
    except ImportError:
        return {"status": "error", "reason": "pywinauto not installed"}

    desktop = Desktop(backend="uia")
    try:
        window = desktop.window(active_only=True)
    except Exception:
        windows = list(desktop.windows())
        window = windows[0] if windows else None

    if not window:
        return {"status": "error", "reason": "No window accessible"}

    import time as _time
    start = _time.time()

    while _time.time() - start < timeout:
        try:
            kwargs = {}
            if name:
                kwargs["title"] = name
            if automation_id:
                kwargs["auto_id"] = automation_id
            if class_name:
                kwargs["class_name"] = class_name
            if control_type:
                kwargs["control_type"] = control_type

            el = window.child_window(**kwargs)
            if el.exists(timeout=1):
                try:
                    r = el.rectangle()
                    rect = {"left": r.left, "top": r.top, "width": r.width(), "height": r.height()}
                except Exception:
                    rect = None

                return {
                    "status": "ok",
                    "found": True,
                    "name": _safe(el, "window_text", ""),
                    "automation_id": _safe(el, "automation_id", ""),
                    "class_name": _safe(el, "class_name", ""),
                    "control_type": getattr(el.element_info, "control_type", "") if hasattr(el, "element_info") else "",
                    "enabled": getattr(el, "is_enabled", lambda: False)(),
                    "rect": rect,
                }
        except Exception:
            pass
        _time.sleep(0.5)

    return {"status": "ok", "found": False, "message": f"Element not found within {timeout}s"}


def _safe(el, attr, default):
    try:
        val = getattr(el, attr)
        return str(val()) if callable(val) else str(val)
    except Exception:
        return default


def main():
    parser = argparse.ArgumentParser(description="Find a UIA element")
    parser.add_argument("--name", help="Element name/title")
    parser.add_argument("--automation-id", help="Automation ID")
    parser.add_argument("--class-name", help="Class name")
    parser.add_argument("--control-type", help="Control type")
    parser.add_argument("--timeout", type=float, default=10.0, help="Search timeout seconds")
    args = parser.parse_args()

    result = find_element(args.name, args.automation_id, args.class_name,
                          args.control_type, args.timeout)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
