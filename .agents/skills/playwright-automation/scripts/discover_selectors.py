#!/usr/bin/env python3
"""
Discover selectors on a web page.
Usage: python discover_selectors.py <url> [--output json]
Reconnaissance-then-action pattern: navigate, wait for stability, inspect, return selectors.
"""
import argparse, asyncio, json, sys
from pathlib import Path


async def discover(url: str, wait_ms: int = 3000) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"status": "error", "reason": "playwright not installed"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(wait_ms)

        title = await page.title()
        current_url = page.url

        # Discover interactive elements with priority-based selectors
        elements = await page.eval_on_selector_all(
            "button, a, input, select, textarea, [role='button'], [role='link'], [data-testid]",
            """els => els.map(el => {
                const tag = el.tagName.toLowerCase();
                const text = (el.textContent || '').trim().slice(0, 60);
                const testid = el.getAttribute('data-testid');
                const ariaLabel = el.getAttribute('aria-label');
                const name = el.getAttribute('name');
                const placeholder = el.getAttribute('placeholder');
                const id = el.id || null;

                let best_selector = null;
                let strategy = null;
                if (testid) { best_selector = `[data-testid="${testid}"]`; strategy = 'data-testid'; }
                else if (ariaLabel) { best_selector = `[aria-label="${ariaLabel}"]`; strategy = 'aria-label'; }
                else if (name) { best_selector = `[name="${name}"]`; strategy = 'name'; }
                else if (placeholder) { best_selector = `[placeholder="${placeholder}"]`; strategy = 'placeholder'; }
                else if (text) { best_selector = `${tag}:has-text("${text.slice(0,20)}")`; strategy = 'text'; }
                else if (id && !/^\\d/.test(id) && id.length < 30) { best_selector = `#${id}`; strategy = 'id'; }

                return {
                    tag, text, testid, ariaLabel, name, placeholder, id,
                    best_selector, strategy,
                    type: el.getAttribute('type'),
                    href: tag === 'a' ? el.getAttribute('href')?.slice(0, 100) : null,
                    visible: el.offsetParent !== null,
                };
            })"""
        )

        # Score by stability
        stability = {"data-testid": 5, "aria-label": 4, "name": 4, "placeholder": 3, "text": 2, "id": 2}
        sorted_elements = sorted(
            [e for e in elements if e["best_selector"]],
            key=lambda e: stability.get(e["strategy"], 0),
            reverse=True,
        )

        await browser.close()

        return {
            "status": "ok",
            "url": current_url,
            "title": title,
            "total_elements": len(elements),
            "elements_with_selectors": len(sorted_elements),
            "selectors": sorted_elements[:100],
        }


def main():
    parser = argparse.ArgumentParser(description="Discover selectors on a web page")
    parser.add_argument("url", help="URL to inspect")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--wait", type=int, default=3000, help="Wait ms after load")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    args = parser.parse_args()

    result = asyncio.run(discover(args.url, args.wait))

    if args.compact:
        print(json.dumps([s["best_selector"] for s in result.get("selectors", [])], indent=2))
    else:
        print(json.dumps(result, indent=2, default=str))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, default=str))
        print(f"\nSaved to: {args.output}")


if __name__ == "__main__":
    main()
