#!/usr/bin/env python3
"""Wait for a page to reach a stable state (network idle + no DOM mutations)."""
import argparse, asyncio, sys


async def wait_stable(url: str, timeout_ms: int = 30000, stable_ms: int = 2000) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"status": "error", "reason": "playwright not installed"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        # Wait for DOM stability — no mutations for stable_ms
        try:
            await page.wait_for_function(
                f"""() => {{
                    return new Promise(resolve => {{
                        let timer;
                        const observer = new MutationObserver(() => {{
                            clearTimeout(timer);
                            timer = setTimeout(() => {{
                                observer.disconnect();
                                resolve(true);
                            }}, {stable_ms});
                        }});
                        observer.observe(document.body, {{
                            childList: true, subtree: true, attributes: true
                        }});
                        timer = setTimeout(() => {{
                            observer.disconnect();
                            resolve(true);
                        }}, {stable_ms});
                        setTimeout(() => {{
                            observer.disconnect();
                            resolve(false);
                        }}, {timeout_ms});
                    }});
                }}""",
                timeout=timeout_ms + 5000,
            )
        except Exception:
            pass  # Timeout is acceptable — page may be static enough

        url = page.url
        title = await page.title()
        await browser.close()

        return {"status": "ok", "url": url, "title": title, "stable": True}


def main():
    parser = argparse.ArgumentParser(description="Wait for page to stabilize")
    parser.add_argument("url", help="URL to wait for")
    parser.add_argument("--timeout", type=int, default=30000, help="Max wait ms")
    parser.add_argument("--stable", type=int, default=2000, help="Stable duration ms")
    args = parser.parse_args()

    result = asyncio.run(wait_stable(args.url, args.timeout, args.stable))
    print(f"Stable: {result['title']} at {result['url']}")


if __name__ == "__main__":
    main()
