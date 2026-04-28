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
        help="Only verify that the Python Playwright package is importable",
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
        print("Playwright Python package is installed")
        return 0

    return subprocess.call([sys.executable, "-m", "playwright", "install", args.browser])


if __name__ == "__main__":
    raise SystemExit(main())
