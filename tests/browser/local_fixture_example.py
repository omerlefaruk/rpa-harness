"""
Deterministic local browser automation example.
"""

import tempfile
from pathlib import Path

from harness import AutomationTestCase, PlaywrightDriver


class LocalFixtureBrowserTest(AutomationTestCase):
    name = "local_fixture_browser"
    tags = ["browser", "playwright", "example", "local"]

    async def setup(self):
        try:
            import playwright.async_api  # noqa: F401
        except ModuleNotFoundError:
            self.driver = None
            self._tmpdir = None
            self.skip(
                "Playwright is not installed. Install with: "
                "python3 -m pip install playwright && python3 -m playwright install chromium"
            )
            return

        self._tmpdir = tempfile.TemporaryDirectory()
        self.page_path = Path(self._tmpdir.name) / "local_fixture.html"
        self.page_path.write_text(
            """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Local Fixture</title>
</head>
<body>
  <main>
    <h1 data-testid="heading">Local browser fixture</h1>
    <button type="button" data-testid="submit-button">Submit</button>
    <p data-testid="status" hidden>Submitted</p>
  </main>
  <script>
    document.querySelector("[data-testid='submit-button']").addEventListener("click", () => {
      document.querySelector("[data-testid='status']").hidden = false;
    });
  </script>
</body>
</html>
""",
            encoding="utf-8",
        )
        self.driver = await PlaywrightDriver.launch(config=self.config)

    async def run(self):
        self.step("Navigate to local fixture")
        await self.driver.goto(self.page_path.as_uri())

        self.step("Verify heading")
        heading = await self.driver.get_text("[data-testid='heading']")
        self.expect(heading == "Local browser fixture", f"Unexpected heading: {heading}")

        self.step("Submit fixture")
        await self.driver.click("[data-testid='submit-button']")

        self.step("Verify submitted state")
        visible = await self.driver.is_visible("[data-testid='status']")
        self.expect(visible, "Submitted state should be visible")

        self.step("Take screenshot")
        path = await self.driver.screenshot(name="local_fixture_browser.png")
        self.result.screenshots.append(path)

    async def teardown(self):
        if getattr(self, "driver", None):
            await self.driver.close()
        if getattr(self, "_tmpdir", None):
            self._tmpdir.cleanup()
