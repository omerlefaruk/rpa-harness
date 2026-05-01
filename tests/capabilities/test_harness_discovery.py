"""Capability characterization for AutomationTestCase discovery and execution."""

from pathlib import Path

import pytest

from harness.config import HarnessConfig
from harness.orchestrator import AutomationHarness
from harness.test_case import AutomationTestCase


def _config(tmp_path: Path) -> HarnessConfig:
    return HarnessConfig(
        headless=True,
        enable_vision=False,
        report_dir=str(tmp_path / "reports"),
        screenshot_dir=str(tmp_path / "screenshots"),
    )


def test_automation_harness_discovers_test_case_subclasses(tmp_path):
    test_file = tmp_path / "discovered_tests.py"
    test_file.write_text(
        """
from harness.test_case import AutomationTestCase


class DiscoveredCapabilityTest(AutomationTestCase):
    name = "discovered_capability"
    tags = ["capability", "discovery"]

    async def run(self):
        self.step("run discovered test")


class HelperOnly:
    pass
""",
        encoding="utf-8",
    )
    harness = AutomationHarness(_config(tmp_path))

    discovered = harness.discover_tests(str(tmp_path))

    assert [test.name for test in discovered] == ["discovered_capability"]


@pytest.mark.asyncio
async def test_tags_and_test_name_filters_select_expected_tests(tmp_path):
    events: list[str] = []

    class BrowserCapabilityTest(AutomationTestCase):
        name = "browser_capability"
        tags = ["browser", "capability"]

        async def run(self):
            events.append(self.name)

    class ApiCapabilityTest(AutomationTestCase):
        name = "api_capability"
        tags = ["api", "capability"]

        async def run(self):
            events.append(self.name)

    harness = AutomationHarness(_config(tmp_path))
    harness.add_test(BrowserCapabilityTest)
    harness.add_test(ApiCapabilityTest)

    tag_results = await harness.run(tags=["browser"])
    name_results = await harness.run(test_names=["api_capability"])

    assert [result.name for result in tag_results] == ["browser_capability"]
    assert [result.name for result in name_results] == ["api_capability"]
    assert events == ["browser_capability", "api_capability"]


@pytest.mark.asyncio
async def test_external_tests_are_excluded_from_default_runs(tmp_path, monkeypatch):
    monkeypatch.delenv("RPA_RUN_EXTERNAL_TESTS", raising=False)
    events: list[str] = []

    class LocalCapabilityTest(AutomationTestCase):
        name = "local_capability"
        tags = ["browser", "capability"]

        async def run(self):
            events.append(self.name)

    class ExternalCapabilityTest(AutomationTestCase):
        name = "external_capability"
        tags = ["browser", "external", "public-site"]

        async def run(self):
            events.append(self.name)

    harness = AutomationHarness(_config(tmp_path))
    harness.add_test(LocalCapabilityTest)
    harness.add_test(ExternalCapabilityTest)

    default_results = await harness.run()
    external_results = await harness.run(tags=["external"])

    assert [result.name for result in default_results] == ["local_capability"]
    assert [result.name for result in external_results] == ["external_capability"]
    assert events == ["local_capability", "external_capability"]


@pytest.mark.asyncio
async def test_setup_run_teardown_order_and_step_logs(tmp_path):
    events: list[str] = []

    class OrderedLifecycleTest(AutomationTestCase):
        name = "ordered_lifecycle"
        tags = ["capability"]

        async def setup(self):
            events.append("setup")

        async def run(self):
            events.append("run")
            self.step("first action")
            self.step("second action")

        async def teardown(self):
            events.append("teardown")

    result = await AutomationHarness(_config(tmp_path))._run_single(OrderedLifecycleTest)

    assert result.passed
    assert events == ["setup", "run", "teardown"]
    assert result.logs == ["Step 1: first action", "Step 2: second action"]


@pytest.mark.asyncio
async def test_teardown_error_is_logged_without_hiding_original_failure(tmp_path):
    class FailingRunAndTeardownTest(AutomationTestCase):
        name = "failing_run_and_teardown"
        tags = ["capability"]

        async def run(self):
            self.step("raise original failure")
            raise ValueError("original failure")

        async def teardown(self):
            raise RuntimeError("teardown failure")

    result = await AutomationHarness(_config(tmp_path))._run_single(FailingRunAndTeardownTest)

    assert not result.passed
    assert result.error_message == "original failure"
    assert any("TEARDOWN ERROR: teardown failure" in log for log in result.logs)


@pytest.mark.asyncio
async def test_screenshots_attach_to_test_result(tmp_path):
    screenshot = tmp_path / "screenshots" / "fixture.png"
    screenshot.parent.mkdir()
    screenshot.write_bytes(b"not-a-real-image-but-valid-attachment-path")

    class ScreenshotAttachmentTest(AutomationTestCase):
        name = "screenshot_attachment"
        tags = ["capability"]

        async def run(self):
            self.step("attach screenshot evidence")
            self.result.screenshots.append(str(screenshot))

    result = await AutomationHarness(_config(tmp_path))._run_single(ScreenshotAttachmentTest)

    assert result.passed
    assert result.screenshots == [str(screenshot)]
    assert result.logs == ["Step 1: attach screenshot evidence"]
