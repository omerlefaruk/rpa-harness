#!/usr/bin/env python3
"""Dump Windows UIA element tree for a process or window."""
import argparse, json, sys, time


def main():
    parser = argparse.ArgumentParser(description="Dump UIA element tree")
    parser.add_argument("--process", help="Process name (e.g., Notepad.exe)")
    parser.add_argument("--window-title", help="Window title substring")
    parser.add_argument("--max-depth", type=int, default=3, help="Max tree depth")
    parser.add_argument("--output", "-o", help="Output JSON path")
    args = parser.parse_args()

    if not sys.platform.startswith("win"):
        print(json.dumps({"status": "skipped", "reason": "Windows only — pywinauto required"}))
        return

    try:
        from pywinauto import Desktop
    except ImportError:
        print(json.dumps({"status": "error", "reason": "pywinauto not installed"}))
        sys.exit(1)

    desktop = Desktop(backend="uia")

    if args.window_title:
        window = desktop.window(title_re=f".*{args.window_title}.*")
    elif args.process:
        windows = desktop.windows()
        window = None
        for w in windows:
            try:
                if args.process.lower() in str(getattr(w, "process_name", lambda: "")()).lower():
                    window = w
                    break
            except Exception:
                pass
    else:
        window = desktop.window(active_only=True) or list(desktop.windows())[0]

    if not window:
        print(json.dumps({"status": "error", "reason": "No window found"}))
        return

    def dump(el, depth=0):
        if depth > args.max_depth:
            return {"name": str(getattr(el, "window_text", lambda: "")())[:60], "_truncated": True}
        children = []
        try:
            for child in el.children():
                children.append(dump(child, depth + 1))
        except Exception:
            pass
        return {
            "name": str(getattr(el, "window_text", lambda: "")())[:60],
            "class_name": str(getattr(el, "class_name", lambda: "")())[:40],
            "auto_id": str(getattr(el, "automation_id", lambda: "")())[:40],
            "control_type": getattr(el.element_info, "control_type", "") if hasattr(el, "element_info") else "",
            "enabled": getattr(el, "is_enabled", lambda: False)(),
            "visible": getattr(el, "is_visible", lambda: False)(),
            "rect": None,
            "children": children[:50],
        }

    tree = dump(window)

    if args.output:
        import pathlib
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.output).write_text(json.dumps(tree, indent=2, default=str))

    print(json.dumps({"status": "ok", "depth": args.max_depth, "tree": tree}, indent=2, default=str))


if __name__ == "__main__":
    main()
