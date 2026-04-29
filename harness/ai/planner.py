"""
AI task planner — decomposes natural language task descriptions
into ordered, dependency-aware execution steps.
"""

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from harness.config import HarnessConfig
from harness.logger import HarnessLogger


@dataclass
class PlanStep:
    id: int
    action: str
    description: str
    tool_name: Optional[str] = None
    tool_args: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[int] = field(default_factory=list)
    expected_result: str = ""
    fallback_action: str = ""
    is_critical: bool = True
    max_retries: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "depends_on": self.depends_on,
            "expected_result": self.expected_result,
            "fallback_action": self.fallback_action,
            "is_critical": self.is_critical,
            "max_retries": self.max_retries,
        }


@dataclass
class Plan:
    task: str
    steps: List[PlanStep]
    risk_assessment: str = ""
    estimated_duration: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "risk_assessment": self.risk_assessment,
            "estimated_duration": self.estimated_duration,
            "metadata": self.metadata,
        }

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def get_ready_steps(self, completed_step_ids: set) -> List[PlanStep]:
        return [
            s for s in self.steps
            if s.id not in completed_step_ids
            and all(d in completed_step_ids for d in s.depends_on)
        ]

    def safety_issues(self) -> List[str]:
        issues: List[str] = []
        for step in self.steps:
            if step.is_critical and step.action not in {"verify", "wait", "done"}:
                if not step.expected_result.strip():
                    issues.append(f"step {step.id} missing expected_result")
            if _uses_coordinate_first_args(step.tool_args):
                issues.append(f"step {step.id} uses coordinate-first tool args")
        if self.steps and self.steps[-1].action != "done":
            issues.append("plan missing final done step")
        return issues

    @property
    def safety_score(self) -> float:
        if not self.steps:
            return 0.0
        possible = len(self.steps) + 1
        issues = min(len(self.safety_issues()), possible)
        return round((possible - issues) / possible, 3)


class TaskPlanner:
    def __init__(self, config: Optional[HarnessConfig] = None, tools_description: str = ""):
        self.config = config
        self.logger = HarnessLogger("planner")
        self.tools_description = tools_description or "Browser, desktop, API, vision tools"

    async def plan(self, task: str, context: Optional[str] = None) -> Plan:
        self.logger.info(f"Planning task: {task[:100]}")

        try:
            from openai import OpenAI
            kwargs = self.config.get_openai_client_kwargs() if self.config else {}
            client = OpenAI(**kwargs)

            model = self.config.agent_model if self.config else "gpt-4o"

            system = f"""You are an RPA task planner. Break the task into concrete execution steps.

Available tools:
{self.tools_description}

Return a JSON plan object:
{{
  "risk_assessment": "low|medium|high — brief risk analysis",
  "estimated_duration": "human-readable estimate",
  "steps": [
    {{
      "id": 1,
      "action": "navigate|click|fill|extract|verify|api_call|desktop_click|desktop_type|wait|done",
      "description": "What this step does in human language",
      "tool_name": "Optional hint for which tool to call",
      "tool_args": {{}},
      "depends_on": [],
      "expected_result": "What to expect after this step",
      "fallback_action": "What to do if this step fails",
      "is_critical": true,
      "max_retries": 1
    }}
  ]
}}

Rules:
- Step IDs must be sequential integers starting from 1
- depends_on lists IDs of steps that must complete first
- Prefer stable selectors: data-testid > aria-label > name > id > class
- Include verification steps after every critical action
- For failures, suggest fallback actions
- Use concrete URLs, selectors, and values (not placeholders)"""

            user = f"Task: {task}"
            if context:
                user += f"\n\nContext: {context}"

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.config.agent_temperature if self.config else 0.3,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )

            data = json.loads(response.choices[0].message.content)
            steps = [PlanStep(**s) for s in data.get("steps", [])]

            plan = Plan(
                task=task,
                steps=steps,
                risk_assessment=data.get("risk_assessment", ""),
                estimated_duration=data.get("estimated_duration", ""),
            )
            plan = self._harden_plan(plan)

            self.logger.info(f"Plan created: {plan.step_count} steps, risk={plan.risk_assessment}")
            return plan

        except Exception as e:
            self.logger.warning(f"Planner LLM failed: {e} — using fallback plan")
            return self._fallback_plan(task)

    def _fallback_plan(self, task: str) -> Plan:
        steps = [
            PlanStep(id=1, action="navigate", description=f"Navigate to target for: {task}",
                     expected_result="Page loaded", max_retries=2),
            PlanStep(id=2, action="verify", description=f"Verify page state for: {task}",
                     expected_result="Correct page visible", max_retries=1),
            PlanStep(id=3, action="done", description=f"Complete: {task}",
                     expected_result="Task finished", max_retries=1),
        ]
        return self._harden_plan(Plan(task=task, steps=steps, risk_assessment="low"))

    def _harden_plan(self, plan: Plan) -> Plan:
        for step in plan.steps:
            if step.is_critical and not step.expected_result.strip():
                step.expected_result = f"{step.description} completed"
        if plan.steps and plan.steps[-1].action != "done":
            plan.steps.append(
                PlanStep(
                    id=max(step.id for step in plan.steps) + 1,
                    action="done",
                    description=f"Complete: {plan.task}",
                    expected_result="Task finished",
                    depends_on=[plan.steps[-1].id],
                    is_critical=True,
                )
            )
        plan.metadata["safety_score"] = plan.safety_score
        plan.metadata["safety_issues"] = plan.safety_issues()
        return plan


def _uses_coordinate_first_args(tool_args: Dict[str, Any]) -> bool:
    if not isinstance(tool_args, dict):
        return False
    has_coordinates = "coordinates" in tool_args or {"x", "y"}.issubset(tool_args.keys())
    has_selector = any(key in tool_args for key in ("selector", "locator", "automation_id", "name"))
    return has_coordinates and not has_selector
