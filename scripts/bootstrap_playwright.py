#!/usr/bin/env python3
"""
Install or verify Playwright browser binaries for the RPA harness.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Playwright browsers")
    parser.add_argument(
        "--browser",
        default="chromium",
        choices=["chromium", "firefox", "webkit"],
        help="Browser binary to install",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the Python package and selected browser binary can launch",
    )
    args = parser.parse_args(argv)

    if importlib.util.find_spec("playwright") is None:
        print(
            "Playwright Python package is not installed. Run: "
            "python3 -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    if args.check:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser_type = getattr(playwright, args.browser)
                browser = browser_type.launch(headless=True)
                browser.close()
        except Exception as exc:
            print(
                f"Playwright {args.browser} is not ready: {exc}\n"
                f"Run: {sys.executable} -m playwright install {args.browser}",
                file=sys.stderr,
            )
            return 1
        print(f"Playwright {args.browser} is ready")
        return 0

    return subprocess.call([sys.executable, "-m", "playwright", "install", args.browser])


if __name__ == "__main__":
    raise SystemExit(main())
