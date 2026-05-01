"""
Example Playwright browser automation test.
"""

from harness import AutomationTestCase, PlaywrightDriver


class ExampleBrowserTest(AutomationTestCase):
    name = "example_browser"
    tags = ["browser", "playwright", "example", "external", "public-site"]

    async def setup(self):
        try:
            import playwright.async_api  # noqa: F401
        except ModuleNotFoundError:
            self.driver = None
            self.skip(
                "Playwright is not installed. Install with: "
                "python3 -m pip install playwright && python3 -m playwright install chromium"
            )
            return
        self.driver = await PlaywrightDriver.launch(config=self.config)

    async def run(self):
        self.step("Navigate to example site")
        await self.driver.goto("https://example.com")

        self.step("Verify page loaded")
        title = await self.driver.get_title()
        self.expect(len(title) > 0, "Page should have a title")

        self.step("Take screenshot")
        path = await self.driver.screenshot()
        self.result.screenshots.append(path)

    async def teardown(self):
        if self.driver:
            await self.driver.close()
