"""
Base test case for RPA harness automation.
Supports async lifecycle: setup → run → teardown, with step tracing.
"""

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    name: str
    status: TestStatus = TestStatus.PENDING
    duration_ms: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASSED

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "screenshots": self.screenshots,
            "videos": self.videos,
            "logs": self.logs,
            "metadata": self.metadata,
        }


class AutomationTestCase:
    name: str = "unnamed-test"
    tags: List[str] = []

    def __init__(self, config=None):
        self.config = config
        self.result = TestResult(name=self.name)
        self._step_index = 0
        self._skipped = False

    async def setup(self):
        pass

    async def run(self):
        raise NotImplementedError("Subclasses must implement run()")

    async def teardown(self):
        pass

    def step(self, description: str):
        self._step_index += 1
        msg = f"Step {self._step_index}: {description}"
        self.result.logs.append(msg)
        return self._step_index

    def skip(self, reason: str):
        self._skipped = True
        self.result.status = TestStatus.SKIPPED
        self.result.logs.append(f"SKIPPED: {reason}")

    def expect(self, condition: bool, message: str = ""):
        if not condition:
            self.result.logs.append(f"ASSERT FAILED: {message}")
            raise AssertionError(message)

    async def _execute(self) -> TestResult:
        self.result.start_time = datetime.now()
        self.result.status = TestStatus.RUNNING

        if self._skipped:
            self.result.end_time = datetime.now()
            return self.result

        try:
            await self.setup()
            await self.run()
            self.result.status = TestStatus.PASSED
        except Exception as e:
            self.result.status = TestStatus.FAILED
            self.result.error_message = str(e)
            self.result.stack_trace = traceback.format_exc()
            self.result.logs.append(f"ERROR: {e}")
        finally:
            try:
                await self.teardown()
            except Exception as e:
                self.result.logs.append(f"TEARDOWN ERROR: {e}")

            self.result.end_time = datetime.now()
            if self.result.start_time:
                delta = self.result.end_time - self.result.start_time
                self.result.duration_ms = delta.total_seconds() * 1000

        return self.result

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name}, tags={self.tags})"
