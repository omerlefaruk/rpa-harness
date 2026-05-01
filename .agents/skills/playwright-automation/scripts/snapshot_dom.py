#!/usr/bin/env python3
"""Snapshot the DOM of a web page. Saves full HTML for analysis."""
import argparse, asyncio, sys
from pathlib import Path


async def snapshot(url: str, output: str = None, wait_ms: int = 3000) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"status": "error", "reason": "playwright not installed"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(wait_ms)

        content = await page.content()
        title = await page.title()
        url = page.url

        if output:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(content)

        await browser.close()

        return {
            "status": "ok",
            "url": url,
            "title": title,
            "html_size": len(content),
            "output": output,
        }


def main():
    parser = argparse.ArgumentParser(description="Snapshot DOM of a web page")
    parser.add_argument("url", help="URL to snapshot")
    parser.add_argument("--output", "-o", help="Output HTML file")
    parser.add_argument("--wait", type=int, default=3000, help="Wait ms after load")
    args = parser.parse_args()

    result = asyncio.run(snapshot(args.url, args.output, args.wait))
    print(result["html_size"], "bytes" if not args.output else f"Saved to {args.output}")


if __name__ == "__main__":
    main()
