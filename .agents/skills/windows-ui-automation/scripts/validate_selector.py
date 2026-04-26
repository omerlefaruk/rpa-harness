#!/usr/bin/env python3
"""Validate that a UIA selector works reliably by testing it multiple times."""
import argparse, json, sys


def validate_selector(name: str = None, automation_id: str = None, class_name: str = None,
                      control_type: str = None, trials: int = 5, timeout: float = 5.0) -> dict:
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
    successes = 0
    durations = []

    for trial in range(trials):
        start = _time.time()
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
            if el.exists(timeout=timeout):
                successes += 1
            durations.append((_time.time() - start) * 1000)
        except Exception:
            durations.append((_time.time() - start) * 1000)

    return {
        "status": "ok",
        "selector": {"name": name, "automation_id": automation_id, "class_name": class_name, "control_type": control_type},
        "trials": trials,
        "successes": successes,
        "success_rate": round(successes / trials, 2),
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "reliable": successes == trials,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate a UIA selector")
    parser.add_argument("--name", help="Element name")
    parser.add_argument("--automation-id", help="Automation ID")
    parser.add_argument("--class-name", help="Class name")
    parser.add_argument("--control-type", help="Control type")
    parser.add_argument("--trials", type=int, default=5, help="Number of validation attempts")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-trial timeout")
    args = parser.parse_args()

    result = validate_selector(args.name, args.automation_id, args.class_name,
                               args.control_type, args.trials, args.timeout)
    print(json.dumps(result, indent=2, default=str))

    if result.get("reliable"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
