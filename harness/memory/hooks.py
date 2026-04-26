"""
Memory lifecycle hooks — session/step/error/end dispatchers.
"""

import traceback
from typing import Any, Dict, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger


class MemoryHooks:
    def __init__(self, memory_engine=None, config: Optional[HarnessConfig] = None):
        self.memory = memory_engine
        self.config = config
        self.logger = HarnessLogger("memory-hooks")
        self._session_id: Optional[str] = None
        self._step_counter: int = 0

    def on_session_start(self, workflow_name: str, task: str = "",
                         config_snapshot: str = ""):
        if not self.memory:
            return
        self._session_id = self.memory.start_session(workflow_name, task, config_snapshot)
        self._step_counter = 0

    async def on_step_start(self, step_name: str):
        self._step_counter += 1

    async def on_post_step(self, step_name: str, action: str = "",
                           tool_used: str = "", tool_args: dict = None,
                           success: bool = True, error_message: str = "",
                           selector_used: str = "", selector_healed: str = "",
                           duration_ms: float = 0, screenshot_path: str = "",
                           output_summary: str = "", url_pattern: str = ""):
        if not self.memory:
            return

        error_category = ""
        if not success and error_message:
            from harness.resilience.errors import classify_error
            class DummyError(Exception):
                pass
            dummy = DummyError(error_message)
            error_category = classify_error(dummy)

        self.memory.capture_observation(
            step_id=self._step_counter,
            step_name=step_name,
            action=action,
            tool_used=tool_used,
            tool_args=tool_args or {},
            success=success,
            error_message=error_message,
            error_category=error_category,
            selector_used=selector_used,
            selector_healed=selector_healed,
            duration_ms=duration_ms,
            screenshot_path=screenshot_path,
            output_summary=output_summary,
        )

        if selector_used and success and url_pattern:
            self.memory.cache_selector(
                url_pattern=url_pattern,
                selector=selector_used,
                element_description=step_name,
                success=True,
            )

        if not success and error_message:
            self.memory.learn_error(
                error_message=error_message,
                error_category=error_category,
                success=False,
            )

    async def on_session_end(self, status: str = "passed",
                             total_steps: int = 0, successful_steps: int = 0,
                             failed_steps: int = 0, duration_seconds: float = 0,
                             summary: Optional[Dict[str, Any]] = None):
        if not self.memory:
            return

        self.memory.end_session(
            status=status,
            total_steps=total_steps or self._step_counter,
            successful_steps=successful_steps,
            failed_steps=failed_steps,
            duration_seconds=duration_seconds,
            summary_text=str(summary)[:500] if summary else "",
        )
        self._session_id = None
        self._step_counter = 0
