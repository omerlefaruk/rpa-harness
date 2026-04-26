#!/usr/bin/env python3
"""
Dump Windows UIA element tree for a window or process.
Usage: python dump_uia_tree.py --window-title "Notepad" --max-depth 3
"""
import argparse, json, sys, time
from pathlib import Path


def dump_tree(process: str = None, window_title: str = None, max_depth: int = 3) -> dict:
    if not sys.platform.startswith("win"):
        return {"status": "skipped", "reason": "Windows only"}

    try:
        from pywinauto import Desktop
    except ImportError:
        return {"status": "error", "reason": "pywinauto not installed — pip install pywinauto"}

    desktop = Desktop(backend="uia")

    if window_title:
        try:
            window = desktop.window(title_re=f".*{window_title}.*")
        except Exception:
            return {"status": "error", "reason": f"Window with title '{window_title}' not found"}
    elif process:
        windows = desktop.windows()
        window = None
        for w in windows:
            try:
                pn = str(getattr(w, "process_name", lambda: "")())
                if process.lower() in pn.lower():
                    window = w
                    break
            except Exception:
                pass
        if not window:
            return {"status": "error", "reason": f"No window found for process '{process}'"}
    else:
        try:
            window = desktop.window(active_only=True)
        except Exception:
            windows = list(desktop.windows())
            window = windows[0] if windows else None

    if not window:
        return {"status": "error", "reason": "No window accessible"}

    element_count = [0]

    def dump(el, depth=0):
        element_count[0] += 1
        if depth > max_depth:
            return {"name": _safe(el, "window_text", "")[:60], "_truncated": True}

        children = []
        try:
            for child in el.children()[:50]:
                children.append(dump(child, depth + 1))
        except Exception:
            pass

        rect = None
        try:
            r = el.rectangle()
            rect = {"left": r.left, "top": r.top, "width": r.width(), "height": r.height()}
        except Exception:
            pass

        return {
            "name": _safe(el, "window_text", "")[:60],
            "class_name": _safe(el, "class_name", "")[:40],
            "automation_id": _safe(el, "automation_id", "")[:40],
            "control_type": getattr(el.element_info, "control_type", "") if hasattr(el, "element_info") else "",
            "enabled": getattr(el, "is_enabled", lambda: False)(),
            "visible": getattr(el, "is_visible", lambda: False)(),
            "rect": rect,
            "children": children,
        }

    def _safe(el, attr, default):
        try:
            val = getattr(el, attr)
            return str(val()) if callable(val) else str(val)
        except Exception:
            return default

    tree = dump(window)
    return {
        "status": "ok",
        "total_elements": element_count[0],
        "max_depth": max_depth,
        "tree": tree,
    }


def main():
    parser = argparse.ArgumentParser(description="Dump Windows UIA element tree")
    parser.add_argument("--process", help="Process name (e.g., Notepad.exe)")
    parser.add_argument("--window-title", help="Window title substring")
    parser.add_argument("--max-depth", type=int, default=3, help="Max tree depth")
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    args = parser.parse_args()

    result = dump_tree(args.process, args.window_title, args.max_depth)

    if args.compact:
        # Extract just element names and automation IDs
        names = []

        def collect(el):
            if el.get("name"):
                names.append({"name": el["name"], "auto_id": el.get("automation_id", ""),
                              "control_type": el.get("control_type", "")})
            for c in el.get("children", []):
                collect(c)

        if "tree" in result:
            collect(result["tree"])
        print(json.dumps(names, indent=2))
    else:
        print(json.dumps(result, indent=2, default=str))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to: {args.output}")


if __name__ == "__main__":
    main()
