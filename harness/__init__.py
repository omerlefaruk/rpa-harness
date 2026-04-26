"""
RPA Harness — AI-powered UI automation framework.
Optimized for Playwright (browser), Windows UIAutomation (desktop),
API integrations, Excel-driven workflows, agentic AI loop,
persistent memory, subagent dispatch, and web dashboard.
"""

__version__ = "0.1.0"

from harness.config import HarnessConfig, ModelConfig, SubagentConfig, MemoryConfig
from harness.logger import HarnessLogger
from harness.test_case import AutomationTestCase, TestResult, TestStatus
from harness.rpa.workflow import RPAWorkflow, WorkflowResult, WorkflowStatus, WorkflowStep, StepStatus
from harness.rpa.excel import ExcelHandler, ExcelRow
from harness.rpa.queue import JobQueue, Job, JobStatus
from harness.drivers.playwright import PlaywrightDriver
from harness.drivers.windows_ui import WindowsUIDriver, UIElement
from harness.drivers.api import APIDriver
from harness.ai.vision import VisionEngine, DetectedElement
from harness.ai.agent import RPAAgent
from harness.ai.tools import ToolRegistry, Tool, build_default_tools
from harness.orchestrator import AutomationHarness
from harness.reporting import HTMLReporter, JSONReporter

__all__ = [
    "HarnessConfig", "ModelConfig", "SubagentConfig", "MemoryConfig",
    "HarnessLogger",
    "AutomationTestCase", "TestResult", "TestStatus",
    "RPAWorkflow", "WorkflowResult", "WorkflowStatus", "WorkflowStep", "StepStatus",
    "ExcelHandler", "ExcelRow",
    "JobQueue", "Job", "JobStatus",
    "PlaywrightDriver",
    "WindowsUIDriver", "UIElement",
    "APIDriver",
    "VisionEngine", "DetectedElement",
    "RPAAgent",
    "ToolRegistry", "Tool", "build_default_tools",
    "AutomationHarness",
    "HTMLReporter", "JSONReporter",
]
