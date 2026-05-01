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


def test_discovery_supports_dataclass_helpers_with_future_annotations(tmp_path):
    test_file = tmp_path / "dataclass_tests.py"
    test_file.write_text(
        """
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from harness.test_case import AutomationTestCase


@dataclass
class DataclassHelper:
    label: Optional[str] = None
    values: List[str] = field(default_factory=list)


class DataclassCapabilityTest(AutomationTestCase):
    name = "dataclass_capability"
    tags = ["capability", "discovery"]

    async def run(self):
        self.step(DataclassHelper(label="ok").label or "missing")
""",
        encoding="utf-8",
    )
    harness = AutomationHarness(_config(tmp_path))

    discovered = harness.discover_tests(str(tmp_path))

    assert [test.name for test in discovered] == ["dataclass_capability"]


def test_workflow_discovery_supports_dataclass_helpers_with_future_annotations(tmp_path):
    workflow_file = tmp_path / "dataclass_workflows.py"
    workflow_file.write_text(
        """
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from harness.rpa.workflow import RPAWorkflow


@dataclass
class WorkflowHelper:
    kind: ClassVar[str] = "helper"
    label: str = "ok"


class DataclassWorkflow(RPAWorkflow):
    name = "dataclass_workflow"
    tags = ["rpa", "capability", "discovery"]

    def get_records(self):
        return iter([])

    async def process_record(self, record):
        return {"status": WorkflowHelper().label}
""",
        encoding="utf-8",
    )
    harness = AutomationHarness(_config(tmp_path))

    discovered = harness.discover_workflows(str(tmp_path))

    assert [workflow.name for workflow in discovered] == ["dataclass_workflow"]


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
    assert result.metadata["last_successful_step"] == {"index": 2, "description": "second action"}
    assert result.metadata["steps"] == [
        {"index": 1, "description": "first action", "status": "passed"},
        {"index": 2, "description": "second action", "status": "passed"},
    ]


@pytest.mark.asyncio
async def test_failed_test_records_failed_and_last_successful_step_context(tmp_path):
    class StepContextFailureTest(AutomationTestCase):
        name = "step_context_failure"
        tags = ["capability"]

        async def run(self):
            self.step("open application")
            self.step("submit form")
            raise RuntimeError("submit failed")

    result = await AutomationHarness(_config(tmp_path))._run_single(StepContextFailureTest)

    assert not result.passed
    assert result.metadata["last_successful_step"] == {"index": 1, "description": "open application"}
    assert result.metadata["failed_step"] == {"index": 2, "description": "submit form"}
    assert result.metadata["steps"] == [
        {"index": 1, "description": "open application", "status": "passed"},
        {"index": 2, "description": "submit form", "status": "failed"},
    ]


@pytest.mark.asyncio
async def test_skip_during_run_preserves_skipped_status_and_step_context(tmp_path):
    class SkippedDuringRunTest(AutomationTestCase):
        name = "skipped_during_run"
        tags = ["capability"]

        async def run(self):
            self.step("check precondition")
            self.skip("precondition unavailable")

    result = await AutomationHarness(_config(tmp_path))._run_single(SkippedDuringRunTest)

    assert result.status == result.status.SKIPPED
    assert result.metadata["steps"] == [
        {"index": 1, "description": "check precondition", "status": "skipped"},
    ]


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
