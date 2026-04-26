"""
Planner subagent — task decomposition and dependency ordering.
Uses powerful model for complex planning.
"""

from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from subagents.base import BaseSubagent, SubagentResult


class PlannerSubagent(BaseSubagent):
    subagent_name = "planner"
    default_model = "powerful"

    async def run(self, prompt: str, context: str = "") -> SubagentResult:
        self.logger.info(f"Planner task: {prompt[:100]}")

        try:
            client = self._get_client()

            system = """You are an RPA task planner subagent. Decompose tasks into ordered steps.

Return JSON:
{
  "task_summary": "Brief summary",
  "risk_assessment": "low|medium|high — why",
  "estimated_duration": "human-readable estimate",
  "prerequisites": ["things needed before starting"],
  "steps": [
    {
      "id": 1,
      "action": "navigate|click|fill|extract|verify|api_call|desktop_click|wait|done",
      "description": "Human-readable description",
      "tool_hint": "Which tool to use (browser_navigate, browser_click, etc.)",
      "depends_on": [],
      "expected_result": "What to verify",
      "fallback": "What to do if this fails",
      "is_critical": true
    }
  ],
  "dependencies_description": "How steps depend on each other"
}

Rules:
- IDs are sequential starting from 1
- depends_on lists IDs that must complete first
- Every critical action must have a verification step
- Prefer stable selectors over brittle ones
- Include error recovery paths for external operations"""

            user = f"Task: {prompt}"
            if context:
                user += f"\n\nContext: {context}"

            response = client.chat.completions.create(
                model=self._model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self._temperature(),
                max_tokens=3000,
                response_format={"type": "json_object"},
            )

            data = self._parse_json_response(response.choices[0].message.content)
            self.logger.info(f"Planner created {len(data.get('steps', []))} steps (risk: {data.get('risk_assessment', 'unknown')})")
            return SubagentResult(success=True, data=data)

        except Exception as e:
            self.logger.error(f"Planner failed: {e}")
            return SubagentResult(success=False, data={}, error=str(e))
