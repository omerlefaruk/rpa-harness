"""
Memory compress — AI-powered session summarization and embedding generation.
"""

import json
from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger


class MemoryCompressor:
    def __init__(self, config: Optional[HarnessConfig] = None, memory_db=None):
        self.config = config
        self.logger = HarnessLogger("memory-compress")
        self.db = memory_db
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = self.config.get_openai_client_kwargs() if self.config else {}
            self._client = OpenAI(**kwargs)
        return self._client

    async def compress_session(self, session_id: str) -> Dict[str, Any]:
        observations = self._get_session_observations(session_id)
        if not observations:
            return {"summary": "Empty session", "embedding": None}

        summary = await self._generate_summary(observations)
        self._store_summary(session_id, summary)

        return {"summary": summary, "observations_count": len(observations)}

    def _get_session_observations(self, session_id: str) -> List[Dict[str, Any]]:
        if not self.db or not self.db._conn:
            return []

        rows = self.db._conn.execute(
            """SELECT step_name, action, tool_used, success, error_message,
               selector_used, duration_ms
               FROM observations WHERE session_id = ? ORDER BY id""",
            (session_id,),
        ).fetchall()

        return [
            {
                "step": r[0], "action": r[1], "tool": r[2],
                "success": bool(r[3]), "error": r[4] or "",
                "selector": r[5] or "", "duration_ms": r[6],
            }
            for r in rows
        ]

    async def _generate_summary(self, observations: List[Dict[str, Any]]) -> str:
        data = json.dumps(observations, default=str)

        try:
            client = self._get_client()
            model = self.config.memory.compression_model if self.config else "gpt-4o-mini"

            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "system",
                    "content": "Summarize this RPA session. Include: workflow type, steps taken, selectors used, errors encountered, and key outcomes. Keep under 300 words.",
                }, {
                    "role": "user",
                    "content": data[:4000],
                }],
                temperature=0.1,
                max_tokens=500,
            )

            return response.choices[0].message.content
        except Exception as e:
            self.logger.warning(f"Summary generation failed: {e}")
            return self._fallback_summary(observations)

    @staticmethod
    def _fallback_summary(observations: List[Dict[str, Any]]) -> str:
        total = len(observations)
        successful = sum(1 for o in observations if o["success"])
        failed = total - successful

        tools_used = list(set(o["tool"] for o in observations if o["tool"]))
        selectors = list(set(o["selector"] for o in observations if o["selector"]))[:5]

        return json.dumps({
            "total_steps": total,
            "successful": successful,
            "failed": failed,
            "tools_used": tools_used,
            "selectors": selectors,
        })

    def _store_summary(self, session_id: str, summary: str):
        if not self.db:
            return
        self.db._conn.execute(
            "UPDATE sessions SET summary_text = ? WHERE id = ?",
            (summary, session_id),
        )
        self.db._conn.commit()
        self.db.add_session_context(session_id, "summary", summary)
