"""
Core orchestrator for the RPA Harness.
Tests: discovers, runs, reports.
Workflows: discovers, executes, reports.
Agent: plans and executes tasks with AI loop.
"""

import inspect
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.test_case import AutomationTestCase, TestResult, TestStatus
from harness.rpa.workflow import RPAWorkflow, WorkflowResult, WorkflowStatus
from harness.reporting import HTMLReporter, JSONReporter


class AutomationHarness:
    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig.from_env()
        self.logger = HarnessLogger("orchestrator")
        self.test_classes: List[Type[AutomationTestCase]] = []
        self.workflow_classes: List[Type[RPAWorkflow]] = []
        self.results: List[TestResult] = []
        self.workflow_results: List[WorkflowResult] = []
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None

    def discover_tests(self, path: str, pattern: str = "*.py") -> List[Type[AutomationTestCase]]:
        self.logger.info(f"Discovering tests in: {path}")
        test_dir = Path(path)
        discovered = []

        if not test_dir.exists():
            self.logger.warning(f"Test directory not found: {path}")
            return discovered

        import importlib.util
        for file_path in test_dir.rglob(pattern):
            if file_path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(file_path.stem, str(file_path))
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, AutomationTestCase)
                        and obj is not AutomationTestCase
                        and not getattr(obj, "__abstractmethods__", False)
                    ):
                        discovered.append(obj)
                        self.logger.info(f"  Found test: {obj.name}")
            except Exception as e:
                self.logger.warning(f"Failed to load {file_path}: {e}")

        self.test_classes = discovered
        return discovered

    def discover_workflows(self, path: str, pattern: str = "*.py") -> List[Type[RPAWorkflow]]:
        self.logger.info(f"Discovering workflows in: {path}")
        wf_dir = Path(path)
        discovered = []

        if not wf_dir.exists():
            self.logger.warning(f"Workflow directory not found: {path}")
            return discovered

        import importlib.util
        for file_path in wf_dir.rglob(pattern):
            if file_path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(file_path.stem, str(file_path))
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, RPAWorkflow)
                        and obj is not RPAWorkflow
                        and not getattr(obj, "__abstractmethods__", False)
                    ):
                        discovered.append(obj)
                        self.logger.info(f"  Found workflow: {obj.name}")
            except Exception as e:
                self.logger.warning(f"Failed to load {file_path}: {e}")

        self.workflow_classes = discovered
        return discovered

    def add_test(self, test_class: Type[AutomationTestCase]):
        self.test_classes.append(test_class)

    def add_workflow(self, workflow_class: Type[RPAWorkflow]):
        self.workflow_classes.append(workflow_class)

    async def run(self, tags: Optional[List[str]] = None,
                  test_names: Optional[List[str]] = None) -> List[TestResult]:
        self.config.ensure_dirs()
        self.results = []
        self._start_time = time.time()

        to_run = self.test_classes
        if tags:
            to_run = [t for t in to_run if any(tag in getattr(t, "tags", []) for tag in tags)]
        if test_names:
            to_run = [t for t in to_run if t.name in test_names]

        self.logger.info(f"Running {len(to_run)} test(s)...")
        self.logger.info(
            f"Config: browser={self.config.browser}, headless={self.config.headless}, "
            f"vision={self.config.enable_vision}"
        )

        for test_class in to_run:
            result = await self._run_single(test_class)
            self.results.append(result)
            status_icon = "PASS" if result.passed else "FAIL"
            self.logger.info(f"[{status_icon}] {result.name} ({result.duration_ms:.0f}ms)")

        self._end_time = time.time()
        passed = sum(1 for r in self.results if r.passed)
        self.logger.info(f"Run complete: {passed}/{len(self.results)} passed")
        return self.results

    async def run_workflows(self, tags: Optional[List[str]] = None,
                            workflow_names: Optional[List[str]] = None) -> List[WorkflowResult]:
        self.config.ensure_dirs()
        self.workflow_results = []
        self._start_time = time.time()

        to_run = self.workflow_classes
        if tags:
            to_run = [w for w in to_run if any(tag in getattr(w, "tags", []) for tag in tags)]
        if workflow_names:
            to_run = [w for w in to_run if w.name in workflow_names]

        self.logger.info(f"Running {len(to_run)} workflow(s)...")

        for wf_class in to_run:
            result = await self._run_single_workflow(wf_class)
            self.workflow_results.append(result)
            status_icon = "PASS" if result.passed else "FAIL"
            self.logger.info(
                f"[{status_icon}] {result.name} | "
                f"Records: {result.processed_records}/{result.total_records} passed, "
                f"{result.failed_records} failed ({result.duration_ms:.0f}ms)"
            )

        self._end_time = time.time()
        return self.workflow_results

    async def run_agent(self, task: str, context: Optional[str] = None,
                        playwright_driver=None, windows_driver=None,
                        api_driver=None, memory_engine=None) -> Dict[str, Any]:
        from harness.ai.agent import RPAAgent

        agent = RPAAgent(
            config=self.config,
            playwright_driver=playwright_driver,
            windows_driver=windows_driver,
            api_driver=api_driver,
            memory_engine=memory_engine,
        )

        result = await agent.execute(task, context)
        return result

    async def _run_single(self, test_class: Type[AutomationTestCase]) -> TestResult:
        instance = test_class(config=self.config)
        return await instance._execute()

    async def _run_single_workflow(self, workflow_class: Type[RPAWorkflow]) -> WorkflowResult:
        instance = workflow_class(config=self.config)
        return await instance._execute()

    def report(self, formats: List[str] = None,
               include_workflows: bool = True) -> Dict[str, str]:
        formats = formats or ["html", "json"]
        report_paths = {}

        suite_name = self.config.name
        metadata = {
            "harness_version": "0.1.0",
            "config": {
                "browser": self.config.browser,
                "headless": self.config.headless,
                "enable_vision": self.config.enable_vision,
                "enable_agent": self.config.enable_agent,
            },
            "run_duration_sec": round(self._end_time - self._start_time, 2) if self._end_time else None,
        }

        all_results = list(self.results)
        if include_workflows and self.workflow_results:
            for wf in self.workflow_results:
                tr = TestResult(
                    name=wf.name,
                    status=TestStatus.PASSED if wf.passed else TestStatus.FAILED,
                    duration_ms=wf.duration_ms,
                    start_time=wf.start_time,
                    end_time=wf.end_time,
                    error_message=wf.error_message,
                    stack_trace=wf.stack_trace,
                    screenshots=wf.screenshots,
                    logs=wf.logs,
                    metadata={
                        "type": "rpa_workflow",
                        "total_records": wf.total_records,
                        "processed_records": wf.processed_records,
                        "failed_records": wf.failed_records,
                        "output_files": wf.output_files,
                    },
                )
                all_results.append(tr)

        if "html" in formats:
            reporter = HTMLReporter(self.config.report_dir)
            path = reporter.generate(all_results, suite_name, metadata)
            report_paths["html"] = path
            self.logger.info(f"HTML report: {path}")

        if "json" in formats:
            reporter = JSONReporter(self.config.report_dir)
            path = reporter.generate(all_results, suite_name, metadata)
            report_paths["json"] = path
            self.logger.info(f"JSON report: {path}")

        return report_paths

    def summary(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        wf_summary = None
        if self.workflow_results:
            wf_summary = {
                "total_workflows": len(self.workflow_results),
                "total_records": sum(w.total_records for w in self.workflow_results),
                "processed_records": sum(w.processed_records for w in self.workflow_results),
                "failed_records": sum(w.failed_records for w in self.workflow_results),
                "skipped_records": sum(w.skipped_records for w in self.workflow_results),
            }

        return {
            "tests": {
                "total": len(self.results),
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / len(self.results) * 100, 2) if self.results else 0,
            },
            "workflows": wf_summary,
            "total_duration_ms": round(sum(r.duration_ms for r in self.results), 2),
        }
