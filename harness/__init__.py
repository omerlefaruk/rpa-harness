"""RPA Harness package exports."""

__version__ = "0.1.0"

from harness.config import HarnessConfig, ModelConfig, SubagentConfig
from harness.logger import HarnessLogger
from harness.rpa.excel import ExcelHandler, ExcelRow
from harness.rpa.queue import JobQueue, Job, JobStatus
from harness.drivers.playwright import PlaywrightDriver
from harness.drivers.windows_ui import WindowsUIDriver, UIElement
from harness.drivers.api import APIDriver
from harness.ai.vision import VisionEngine, DetectedElement
from harness.ai.agent import RPAAgent
from harness.ai.tools import ToolRegistry, Tool, build_default_tools
from harness.reporting import HTMLReporter, JSONReporter

__all__ = [
    "HarnessConfig", "ModelConfig", "SubagentConfig",
    "HarnessLogger",
    "ExcelHandler", "ExcelRow",
    "JobQueue", "Job", "JobStatus",
    "PlaywrightDriver",
    "WindowsUIDriver", "UIElement",
    "APIDriver",
    "VisionEngine", "DetectedElement",
    "RPAAgent",
    "ToolRegistry", "Tool", "build_default_tools",
    "HTMLReporter", "JSONReporter",
]
