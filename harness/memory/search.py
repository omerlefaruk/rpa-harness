"""
Memory search — 3-layer progressive disclosure pattern.
Layer 1: index (compact, ~50 tokens/result)
Layer 2: context (timeline, ~200 tokens)
Layer 3: details (full fetch, ~500 tokens)
"""

from typing import Any, Dict, List, Optional

from harness.logger import HarnessLogger


class MemorySearch:
    def __init__(self, memory_db=None):
        self.db = memory_db
        self.logger = HarnessLogger("memory-search")

    def search_index(self, query: str, search_type: str = "all", limit: int = 10) -> List[Dict[str, Any]]:
        """Layer 1: Compact index search."""
        results = self.db.search(query, search_type, limit)

        compact = []
        for r in results:
            item = {"type": r.get("type", "unknown"), "id": r.get("id", "")}
            if r["type"] == "selector":
                item["selector"] = r.get("selector", "")
                item["rate"] = r.get("success_rate", 0)
            elif r["type"] == "observation":
                item["step"] = r.get("step_name", "")[:80]
                item["success"] = r.get("success", False)
            elif r["type"] == "error_pattern":
                item["signature"] = r.get("signature", "")[:60]
                item["category"] = r.get("category", "")
            compact.append(item)

        return compact

    def get_context(self, observation_id: int, window: int = 5) -> Dict[str, Any]:
        """Layer 2: Chronological context around an observation."""
        if not self.db or not self.db._conn:
            return {}

        center = self.db._conn.execute(
            "SELECT id, session_id, step_id, step_name, success FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()

        if not center:
            return {}

        session_id = center[1]
        step_id = center[2]

        before = self.db._conn.execute(
            """SELECT id, step_name, success FROM observations
               WHERE session_id = ? AND step_id < ? ORDER BY step_id DESC LIMIT ?""",
            (session_id, step_id, window),
        ).fetchall()

        after = self.db._conn.execute(
            """SELECT id, step_name, success FROM observations
               WHERE session_id = ? AND step_id > ? ORDER BY step_id ASC LIMIT ?""",
            (session_id, step_id, window),
        ).fetchall()

        session = self.db._conn.execute(
            "SELECT workflow_name, task_description, status FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

        return {
            "session": {"workflow": session[0] if session else "", "status": session[2] if session else ""},
            "observation": {"id": center[0], "step": center[3], "success": bool(center[4])},
            "before": [{"id": r[0], "step": r[1], "success": bool(r[2])} for r in reversed(before)],
            "after": [{"id": r[0], "step": r[1], "success": bool(r[2])} for r in after],
        }

    def get_details(self, observation_ids: List[int]) -> List[Dict[str, Any]]:
        """Layer 3: Full observation details."""
        if not self.db or not self.db._conn:
            return []

        placeholders = ",".join("?" * len(observation_ids))
        rows = self.db._conn.execute(
            f"""SELECT id, session_id, step_name, action, tool_used, tool_args,
               success, error_message, selector_used, selector_healed,
               duration_ms, screenshot_path, output_summary
               FROM observations WHERE id IN ({placeholders})""",
            observation_ids,
        ).fetchall()

        return [
            {
                "id": r[0], "session_id": r[1], "step_name": r[2],
                "action": r[3], "tool_used": r[4], "tool_args": r[5],
                "success": bool(r[6]), "error_message": r[7] or "",
                "selector_used": r[8] or "", "selector_healed": r[9] or "",
                "duration_ms": r[10], "screenshot_path": r[11] or "",
                "output_summary": r[12] or "",
            }
            for r in rows
        ]
