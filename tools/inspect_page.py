#!/usr/bin/env python3
"""Inspect a web page — navigate, screenshot, dump DOM, and discover selectors."""
import argparse, asyncio, json, sys
from pathlib import Path


async def main():
    parser = argparse.ArgumentParser(description="Inspect a web page for selectors")
    parser.add_argument("url", help="URL to inspect")
    parser.add_argument("--output", "-o", default="./runs", help="Output directory")
    parser.add_argument("--wait", type=int, default=3000, help="Wait ms after load")
    args = parser.parse_args()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright not installed. Run: pip install playwright && playwright install")
        sys.exit(1)

    out_dir = Path(args.output) / "page_inspect"
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(args.url, wait_until="networkidle")

        page.wait_for_timeout(args.wait)
        title = await page.title()
        url = page.url

        # Screenshot
        screenshot_path = str(out_dir / "screenshot.png")
        await page.screenshot(path=screenshot_path, full_page=True)

        # DOM snapshot
        content = await page.content()
        dom_path = out_dir / "dom.html"
        dom_path.write_text(content)

        # Discover selectors
        interactive = await page.eval_on_selector_all(
            "button, a, input, select, textarea, [role='button'], [role='link']",
            """els => els.map(el => ({
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().slice(0, 60),
                id: el.id || null,
                className: el.className?.slice(0, 100) || null,
                name: el.getAttribute('name'),
                type: el.getAttribute('type'),
                placeholder: el.getAttribute('placeholder'),
                testid: el.getAttribute('data-testid'),
                aria_label: el.getAttribute('aria-label'),
                role: el.getAttribute('role'),
                href: el.tagName === 'A' ? el.getAttribute('href')?.slice(0, 100) : null,
            }))"""
        )

        result = {
            "url": url,
            "title": title,
            "screenshot": screenshot_path,
            "dom_path": str(dom_path),
            "dom_size": len(content),
            "interactive_elements": len(interactive),
            "elements": interactive[:500],
        }

        result_path = out_dir / "inspect_result.json"
        result_path.write_text(json.dumps(result, indent=2, default=str))

        print(json.dumps({"status": "ok", "url": url, "title": title,
                          "elements_found": len(interactive),
                          "result": str(result_path), "screenshot": screenshot_path}, indent=2))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
