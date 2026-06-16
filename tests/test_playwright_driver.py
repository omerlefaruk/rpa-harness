"""Tests for Playwright driver launch modes."""

import sys
import types

import pytest

from harness.config import HarnessConfig
from harness.drivers.playwright import PlaywrightDriver


@pytest.mark.asyncio
async def test_playwright_driver_attaches_over_cdp(monkeypatch):
    calls = []

    class FakePage:
        pass

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]

        async def new_page(self):
            page = FakePage()
            self.pages.append(page)
            return page

    class FakeBrowser:
        def __init__(self):
            self.contexts = [FakeContext()]

        async def close(self):
            calls.append(("browser.close",))

    class FakeChromium:
        async def connect_over_cdp(self, endpoint):
            calls.append(("connect_over_cdp", endpoint))
            return FakeBrowser()

        async def launch(self, **kwargs):
            calls.append(("launch", kwargs))
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()
            self.firefox = FakeChromium()
            self.webkit = FakeChromium()

        async def stop(self):
            calls.append(("playwright.stop",))

    class FakeStarter:
        async def start(self):
            return FakePlaywright()

    module = types.ModuleType("playwright.async_api")
    module.async_playwright = lambda: FakeStarter()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)

    config = HarnessConfig()
    config.browser_cdp_endpoint = "http://127.0.0.1:9222"

    driver = await PlaywrightDriver.launch(config=config)
    await driver.close()

    assert ("connect_over_cdp", "http://127.0.0.1:9222") in calls
    assert not any(call[0] == "launch" for call in calls)
    assert not any(call[0] == "browser.close" for call in calls)
