"""
Memory engine — main integration point for persistent RPA memory.
Provides session lifecycle, observation capture, selector caching,
error pattern learning, and context injection.
"""

import json
from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.memory.database import MemoryDatabase


class RPAMemory:
    def __init__(self, config: Optional[HarnessConfig] = None, db_path: str = None):
        self.config = config
        self.logger = HarnessLogger("memory")

        if db_path is None and config and config.memory.enabled:
            db_path = config.memory.db_path

        self.db = MemoryDatabase(
            db_path or "./data/memory.db",
            logger=self.logger,
        )
        self._current_session_id: Optional[str] = None

    def start_session(self, workflow_name: str, task: str = "",
                      config_snapshot: str = "") -> str:
        import uuid
        self._current_session_id = str(uuid.uuid4())[:12]
        self.db.create_session(
            self._current_session_id, workflow_name, task, config_snapshot
        )
        self.logger.info(f"Memory session started: {self._current_session_id}")
        return self._current_session_id

    def end_session(self, status: str = "passed", total_steps: int = 0,
                    successful_steps: int = 0, failed_steps: int = 0,
                    duration_seconds: float = 0, summary_text: str = ""):
        if not self._current_session_id:
            return
        self.db.end_session(
            self._current_session_id, status, total_steps,
            successful_steps, failed_steps, duration_seconds, summary_text,
        )
        self.logger.info(f"Memory session ended: {self._current_session_id} ({status})")
        self._current_session_id = None

    def capture_observation(self, step_id: int, step_name: str, action: str = "",
                            tool_used: str = "", tool_args: dict = None,
                            success: bool = True, error_message: str = "",
                            error_category: str = "", selector_used: str = "",
                            selector_healed: str = "", duration_ms: float = 0,
                            screenshot_path: str = "", output_summary: str = ""):
        if not self._current_session_id:
            return

        self.db.add_observation(
            session_id=self._current_session_id,
            step_id=step_id,
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

        if selector_used and success and self._current_session_id:
            # could extract URL pattern from step context
            pass

    def cache_selector(self, url_pattern: str, selector: str,
                       selector_type: str = "css", element_description: str = "",
                       element_type: str = "", success: bool = True):
        self.db.upsert_selector(
            url_pattern=url_pattern,
            selector=selector,
            selector_type=selector_type,
            element_description=element_description,
            element_type=element_type,
            success=success,
        )

    def get_cached_selectors(self, url_pattern: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.db.get_selectors(url_pattern, limit)

    def learn_error(self, error_message: str, error_category: str,
                    recovery_strategy: str = "", success: bool = False):
        signature = _error_signature(error_message)
        self.db.update_error_pattern(
            error_signature=signature,
            error_message=error_message,
            error_category=error_category,
            recovery_strategy=recovery_strategy,
            success=success,
        )

    async def search(self, query: str, search_type: str = "all",
                     limit: int = 10) -> List[Dict[str, Any]]:
        return self.db.search(query, search_type, limit)

    async def inject_context(self, task: str, current_context: str = "",
                             max_items: int = 5) -> Optional[str]:
        if not self.config or not self.config.memory.enabled:
            return None

        results = self.db.search(task, search_type="all", limit=max_items)
        if not results:
            return None

        lines = ["## Relevant past context"]
        for r in results:
            if r["type"] == "selector":
                lines.append(
                    f"- Selector: `{r['selector']}` — {r.get('description', '')} "
                    f"(success rate: {r.get('success_rate', 'N/A')})"
                )
            elif r["type"] == "observation":
                status = "✓" if r.get("success") else "✗"
                lines.append(
                    f"- {status} {r.get('step_name', '')} using {r.get('tool_used', '')}"
                )
                if r.get("error_message"):
                    lines.append(f"  Error: {r['error_message'][:100]}")
            elif r["type"] == "error_pattern":
                lines.append(
                    f"- Error pattern: {r.get('signature', '')[:80]} "
                    f"(strategy: {r.get('strategy', '')})"
                )

        return "\n".join(lines)

    async def capture_session(self, summary: Dict[str, Any]):
        if not self._current_session_id:
            return

        self.db.end_session(
            session_id=self._current_session_id,
            status=summary.get("status", "passed"),
            total_steps=summary.get("total_steps", 0),
            successful_steps=summary.get("successful_steps", 0),
            failed_steps=summary.get("failed_steps", 0),
            duration_seconds=summary.get("duration_seconds", 0),
            summary_text=json.dumps(summary.get("steps", [])[:500], default=str),
        )

    def close(self):
        self.db.close()


def _error_signature(error_message: str) -> str:
    import re
    msg = error_message.lower()
    msg = re.sub(r'[0-9a-f]{8,}', '<HEX>', msg)
    msg = re.sub(r'\d+', '<NUM>', msg)
    return msg[:200]
