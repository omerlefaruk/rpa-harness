"""
Explorer subagent — file reading, codebase search, information gathering.
Uses fast model for efficient scanning.
"""

from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from subagents.base import BaseSubagent, SubagentResult


class ExplorerSubagent(BaseSubagent):
    subagent_name = "explorer"
    default_model = "fast"

    async def run(self, prompt: str, context: str = "") -> SubagentResult:
        self.logger.info(f"Explorer task: {prompt[:100]}")

        try:
            client = self._get_client()

            system = """You are a codebase explorer subagent. Your job is to gather information
from files, directories, and code. Return structured JSON with findings.

For file reading tasks, return:
{
  "findings": [
    {"file": "path/to/file", "key_info": "..."}
  ],
  "summary": "Brief summary of what was found"
}

For search tasks, return:
{
  "matches": [
    {"location": "file:line", "snippet": "..."}
  ],
  "summary": "Brief summary"
}"""

            response = client.chat.completions.create(
                model=self._model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Task: {prompt}\n\nContext: {context}"},
                ],
                temperature=self._temperature(),
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            data = self._parse_json_response(response.choices[0].message.content)
            self.logger.info(f"Explorer found {len(data.get('findings', data.get('matches', [])))} items")
            return SubagentResult(success=True, data=data)

        except Exception as e:
            self.logger.error(f"Explorer failed: {e}")
            return SubagentResult(success=False, data={}, error=str(e))
