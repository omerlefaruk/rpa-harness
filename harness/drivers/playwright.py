"""
Playwright browser automation driver with AI-powered helpers.
Supports full async Playwright API with auto-healing, vision fallback,
network interception, iframes, file operations, and multi-tab.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from harness.config import HarnessConfig
from harness.drivers.base import AbstractBaseDriver
from harness.logger import HarnessLogger


class PlaywrightDriver(AbstractBaseDriver):
    driver_type = "playwright"

    def __init__(self, config: Optional[HarnessConfig] = None):
        super().__init__(config)
        self.page = None
        self.context = None
        self.browser = None
        self._playwright = None
        self._healer = None
        self._tabs: Dict[str, Any] = {}

    @classmethod
    async def launch(cls, config: Optional[HarnessConfig] = None, **kwargs) -> "PlaywrightDriver":
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Playwright browser automation requires Playwright. Install it with: "
                "python3 -m pip install playwright && python3 -m playwright install chromium"
            ) from exc

        self = cls(config=config)
        self._playwright = await async_playwright().start()

        cfg = config
        browser_type = getattr(self._playwright, cfg.browser if cfg else kwargs.get("browser", "chromium"))
        headless = cfg.headless if cfg else kwargs.get("headless", False)
        slow_mo = cfg.slow_mo if cfg else kwargs.get("slow_mo", 0)

        self.browser = await browser_type.launch(headless=headless, slow_mo=slow_mo)

        viewport = {"width": 1920, "height": 1080}
        if cfg:
            viewport = {"width": cfg.viewport_width, "height": cfg.viewport_height}

        self.context = await self.browser.new_context(viewport=viewport)
        self.page = await self.context.new_page()
        self._connected = True
        self.logger.info(f"Browser launched: {cfg.browser if cfg else 'chromium'} (headless={headless})")
        return self

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._connected = False
        self.logger.info("Browser closed")

    async def goto(self, url: str, wait_until: str = "networkidle", timeout: int = 30000):
        self.logger.info(f"Navigate → {url}")
        await self.page.goto(url, wait_until=wait_until, timeout=timeout)

    async def click(self, selector: str, timeout: Optional[int] = None):
        timeout = timeout or 10000
        try:
            await self.page.click(selector, timeout=timeout)
            self.logger.info(f"Clicked: {selector}")
        except Exception as e:
            self.logger.warning(f"Click failed for {selector}: {e}")
            if self.config and self.config.auto_heal_selectors:
                healed = await self._heal(selector, lambda s: self.page.click(s, timeout=timeout))
                if healed:
                    self.logger.info(f"Healed click: {healed}")
                else:
                    raise
            else:
                raise

    async def click_at(self, x: int, y: int):
        await self.page.mouse.click(x, y)
        self.logger.info(f"Clicked at ({x}, {y})")

    async def fill(self, selector: str, value: str, timeout: Optional[int] = None):
        timeout = timeout or 10000
        try:
            await self.page.fill(selector, value, timeout=timeout)
            self.logger.info(f"Filled {selector}: '{str(value)[:50]}'")
        except Exception as e:
            self.logger.warning(f"Fill failed for {selector}: {e}")
            if self.config and self.config.auto_heal_selectors:
                healed = await self._heal(selector, lambda s: self.page.fill(s, value, timeout=timeout))
                if healed:
                    self.logger.info(f"Healed fill: {healed}")
                else:
                    raise
            else:
                raise

    async def type(self, selector: str, text: str, delay: int = 50, timeout: Optional[int] = None):
        await self.page.click(selector, timeout=timeout or 10000)
        await self.page.keyboard.type(text, delay=delay)
        self.logger.info(f"Typed into {selector}")

    async def get_text(self, selector: str, timeout: Optional[int] = None) -> str:
        el = await self.page.wait_for_selector(selector, timeout=timeout or 10000)
        return await el.inner_text()

    async def get_value(self, selector: str, timeout: Optional[int] = None) -> str:
        el = await self.page.wait_for_selector(selector, timeout=timeout or 10000)
        return await el.input_value()

    async def is_visible(self, selector: str, timeout: int = 5000) -> bool:
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            return True
        except Exception:
            return False

    async def is_enabled(self, selector: str, timeout: int = 5000) -> bool:
        try:
            el = await self.page.wait_for_selector(selector, timeout=timeout)
            return await el.is_enabled()
        except Exception:
            return False

    async def wait_for(self, selector: str, timeout: Optional[int] = None,
                       state: str = "visible"):
        await self.page.wait_for_selector(selector, timeout=timeout or 10000, state=state)

    async def wait_for_text(self, text: str, timeout: int = 10000):
        await self.page.wait_for_selector(f"text={text}", timeout=timeout)

    async def wait_for_url(self, url_pattern: str, timeout: int = 10000):
        await self.page.wait_for_url(url_pattern, timeout=timeout)

    async def wait_for_load_state(self, state: str = "networkidle", timeout: int = 30000):
        await self.page.wait_for_load_state(state, timeout=timeout)

    async def select_option(self, selector: str, value: str, timeout: Optional[int] = None):
        await self.page.select_option(selector, value, timeout=timeout or 10000)
        self.logger.info(f"Selected '{value}' in {selector}")

    async def check(self, selector: str, timeout: Optional[int] = None):
        await self.page.check(selector, timeout=timeout or 10000)
        self.logger.info(f"Checked: {selector}")

    async def uncheck(self, selector: str, timeout: Optional[int] = None):
        await self.page.uncheck(selector, timeout=timeout or 10000)
        self.logger.info(f"Unchecked: {selector}")

    async def hover(self, selector: str, timeout: Optional[int] = None):
        await self.page.hover(selector, timeout=timeout or 10000)
        self.logger.info(f"Hovered: {selector}")

    async def press(self, key: str):
        await self.page.keyboard.press(key)

    async def screenshot(self, name: Optional[str] = None, full_page: bool = False) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = name or f"playwright_{ts}.png"
        report_dir = self.config.report_dir if self.config else "./reports"
        path = Path(report_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path), full_page=full_page)
        self._screenshots.append(str(path))
        self.logger.info(f"Screenshot: {path}")
        return str(path)

    async def get_content(self) -> str:
        return await self.page.content()

    async def get_url(self) -> str:
        return self.page.url

    async def get_title(self) -> str:
        return await self.page.title()

    async def extract_data(self, schema: Dict[str, str]) -> Dict[str, Any]:
        result = {}
        for key, selector in schema.items():
            try:
                el = await self.page.query_selector(selector)
                result[key] = await el.inner_text() if el else None
            except Exception as e:
                result[key] = None
                self.logger.warning(f"Failed to extract {key}: {e}")
        return result

    async def extract_table(self, selector: str) -> List[Dict[str, str]]:
        rows = []
        try:
            headers = await self.page.eval_on_selector_all(
                f"{selector} thead th", "ths => ths.map(th => th.textContent.trim())"
            )
            if not headers:
                headers = await self.page.eval_on_selector_all(
                    f"{selector} tr:first-child th, {selector} tr:first-child td",
                    "cells => cells.map(c => c.textContent.trim())",
                )

            row_count = await self.page.eval_on_selector(
                f"{selector} tbody", "tbody => tbody.rows.length"
            ) or await self.page.eval_on_selector(
                selector, "table => table.rows.length"
            )

            for i in range(row_count):
                cells = await self.page.eval_on_selector_all(
                    f"{selector} tr:nth-child({i + 1}) td, {selector} tr:nth-child({i + 1}) th",
                    "cells => cells.map(c => c.textContent.trim())",
                )
                if cells and len(cells) >= len(headers):
                    row = {headers[j]: cells[j] for j in range(len(headers))}
                    rows.append(row)
        except Exception as e:
            self.logger.warning(f"Table extraction failed: {e}")
        return rows

    async def evaluate(self, expression: str, *args) -> Any:
        return await self.page.evaluate(expression, *args)

    async def upload_file(self, selector: str, file_path: str):
        await self.page.set_input_files(selector, file_path)
        self.logger.info(f"Uploaded file: {file_path}")

    async def download_file(self, trigger_selector: str, save_dir: Optional[str] = None) -> str:
        save_dir = save_dir or (self.config.report_dir if self.config else "./downloads")
        Path(save_dir).mkdir(parents=True, exist_ok=True)

        async with self.page.expect_download() as download_info:
            await self.page.click(trigger_selector)

        download = await download_info.value
        path = str(Path(save_dir) / download.suggested_filename)
        await download.save_as(path)
        self.logger.info(f"Downloaded: {path}")
        return path

    async def get_cookies(self) -> List[dict]:
        return await self.context.cookies()

    async def set_cookies(self, cookies: List[dict]):
        await self.context.add_cookies(cookies)

    async def get_local_storage(self) -> dict:
        return await self.page.evaluate("() => JSON.parse(JSON.stringify(localStorage))")

    async def set_local_storage(self, items: dict):
        for key, value in items.items():
            await self.page.evaluate(
                f"localStorage.setItem('{key}', '{value}')"
            )

    async def intercept_request(self, url_pattern: str, handler: Callable[[Any], Any]):
        await self.page.route(url_pattern, handler)

    async def new_tab(self, name: str = "default") -> Any:
        page = await self.context.new_page()
        self._tabs[name] = page
        return page

    async def switch_tab(self, name: str = "default"):
        if name in self._tabs:
            self.page = self._tabs[name]
            await self.page.bring_to_front()
        else:
            self.logger.warning(f"Tab '{name}' not found")

    async def close_tab(self, name: str = "default"):
        if name in self._tabs:
            await self._tabs[name].close()
            del self._tabs[name]
            if name == "default" and self._tabs:
                self.page = next(iter(self._tabs.values()))

    async def ai_action(self, instruction: str, use_vision: bool = True) -> Optional[Any]:
        self.logger.info(f"AI action: {instruction}")
        if use_vision and self.config and self.config.enable_vision:
            from harness.ai.vision import VisionEngine
            screenshot_path = await self.screenshot(name="ai_vision_input.png")
            vision = VisionEngine(config=self.config)
            element = await vision.find_element(screenshot_path, instruction)
            if element:
                await self.click_at(*element.center)
                return element
        raise RuntimeError("ai_action requires vision. Set enable_vision=True and OPENAI_API_KEY.")

    async def _heal(self, broken_selector: str, action_fn: Callable[[str], Any]) -> Optional[str]:
        from harness.selectors.strategies import get_healing_ladder
        self.logger.info(f"Healing selector: {broken_selector}")

        ladder = get_healing_ladder(broken_selector)
        for variant in ladder:
            try:
                await action_fn(variant)
                return variant
            except Exception:
                continue

        if self.config and self.config.enable_vision:
            try:
                screenshot = await self.screenshot(name="heal.png")
                from harness.ai.vision import VisionEngine
                vision = VisionEngine(config=self.config)
                healed = await vision.generate_selector(screenshot, broken_selector)
                if healed:
                    await action_fn(healed)
                    return healed
            except Exception as e:
                self.logger.warning(f"Vision heal failed: {e}")

        return None
