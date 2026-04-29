#!/usr/bin/env python3
"""Run browser selector swarm discovery for a URL."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.selectors.browser_swarm import run_browser_selector_swarm  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape browser page evidence, generate selector candidates, and validate them."
    )
    parser.add_argument("url", help="Target URL, including file:// URLs for local fixtures")
    parser.add_argument("--output", "-o", default="runs/browser_recon", help="Output directory")
    parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    parser.add_argument("--headed", action="store_true", help="Run browser visibly")
    parser.add_argument("--wait-until", default="networkidle", help="Playwright wait_until value")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--intent", help="Element/action intent to prioritize, for example 'Save'")
    parser.add_argument("--safe-click", action="store_true", help="Try clicking candidates")
    parser.add_argument("--expect-url-contains", help="Required URL fragment after safe click")
    parser.add_argument("--expect-text", help="Required visible text after safe click")
    parser.add_argument("--save-raw-html", action="store_true", help="Write redacted DOM artifact")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if args.safe_click and not (args.expect_url_contains or args.expect_text):
        print(
            "--safe-click requires --expect-url-contains or --expect-text",
            file=sys.stderr,
        )
        return 2

    report = await run_browser_selector_swarm(
        args.url,
        output_dir=args.output,
        browser_name=args.browser,
        headless=not args.headed,
        wait_until=args.wait_until,
        timeout_ms=args.timeout_ms,
        max_candidates=args.max_candidates,
        intent=args.intent,
        safe_click=args.safe_click,
        expect_url_contains=args.expect_url_contains,
        expect_text=args.expect_text,
        save_raw_html=args.save_raw_html,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "url": report["url"],
                "interactive_elements": report["summary"]["interactive_elements"],
                "candidates": report["summary"]["candidates"],
                "validated": report["summary"]["validated"],
                "winner": report["validation"]["winner"],
                "report": report["artifacts"]["report"],
                "html_report": report["artifacts"]["html_report"],
                "screenshot": report["artifacts"]["screenshot"],
            },
            indent=2,
            default=str,
        )
    )
    return 0 if report["validation"]["winner"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
