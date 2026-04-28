"""
Agentic AI loop — the core of the RPA Harness.
Implements: plan → observe → decide → act → verify → reflect
"""

import json
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from harness.ai.memory import AgentMemory, MemoryEntry
from harness.ai.planner import Plan, PlanStep, TaskPlanner
from harness.ai.tools import ToolRegistry, build_default_tools
from harness.ai.vision import VisionEngine
from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.resilience.recovery import smart_retry


class RPAAgent:
    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        playwright_driver=None,
        windows_driver=None,
        api_driver=None,
        excel_handler=None,
        vision_engine: Optional[VisionEngine] = None,
        memory_engine=None,
    ):
        self.config = config or HarnessConfig.from_env()
        self.logger = HarnessLogger("agent", jsonl_output=True)

        self.playwright = playwright_driver
        self.windows = windows_driver
        self.api = api_driver
        self.excel = excel_handler

        self.vision = vision_engine or (VisionEngine(config=self.config) if self.config.enable_vision else None)

        tools = build_default_tools(
            playwright_driver=self.playwright,
            windows_driver=self.windows,
            api_driver=self.api,
            excel_handler=self.excel,
            vision_engine=self.vision,
            memory_engine=memory_engine,
        )

        tools_desc = "\n".join(
            f"- {t.name}: {t.description}" for t in tools
        )

        self.tools = ToolRegistry(logger=self.logger)
        self.tools.register_many(tools)
        self.planner = TaskPlanner(config=self.config, tools_description=tools_desc)
        self.memory = AgentMemory(max_history=50)
        self._persistent_memory = memory_engine

        self._max_steps = config.agent_max_steps if config else 50
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = self.config.get_openai_client_kwargs()
            self._client = OpenAI(**kwargs)
        return self._client

    def _model(self) -> str:
        return self.config.agent_model if self.config else "gpt-4o"

    async def execute(self, task: str, context: Optional[str] = None) -> Dict[str, Any]:
        start_time = datetime.now()
        self.logger.info(f"Agent task: {task[:100]}")

        if self._persistent_memory:
            past_context = await self._persistent_memory.inject_context(
                task, context or ""
            )
            if past_context:
                context = (context or "") + "\n\n[Previous session context]\n" + past_context

        plan = await self.planner.plan(task, context)
        self.logger.info(f"Plan: {plan.step_count} steps (risk: {plan.risk_assessment})")

        completed_step_ids: set = set()
        step_results: List[Dict[str, Any]] = []
        step_limit = min(plan.step_count + 5, self._max_steps)

        for _ in range(step_limit):
            ready = plan.get_ready_steps(completed_step_ids)
            if not ready:
                break

            step = ready[0]
            result = await self._execute_step(step, plan)

            completed_step_ids.add(step.id)
            step_results.append(result)

            if result.get("tool_name") == "done":
                break

            if not result.get("success") and step.is_critical:
                self.logger.warning(f"Critical step {step.id} failed — stopping")
                break

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        success = all(r.get("success", False) for r in step_results)

        summary = {
            "task": task,
            "status": "success" if success else "partial",
            "total_steps": len(step_results),
            "successful_steps": sum(1 for r in step_results if r.get("success")),
            "failed_steps": sum(1 for r in step_results if not r.get("success")),
            "duration_seconds": round(duration, 2),
            "steps": step_results,
            "memory_summary": self.memory.summarize(),
        }

        if self._persistent_memory:
            await self._persistent_memory.capture_session(summary)

        self.logger.info(f"Agent complete: {summary['successful_steps']}/{summary['total_steps']} steps passed ({duration:.1f}s)")
        return summary

    async def _execute_step(self, step: PlanStep, plan: Plan) -> Dict[str, Any]:
        self.logger.step(step.id, step.description)

        start = datetime.now()
        result = {
            "step_id": step.id,
            "action": step.action,
            "description": step.description,
            "success": False,
            "tool_name": None,
            "tool_args": {},
            "output": None,
            "error": None,
            "retries": 0,
            "duration_ms": 0,
        }

        needs_decision = not step.tool_name or step.action in ("verify", "done")

        attempts = 0

        async def run_tool(tool_name_override: Optional[str] = None,
                           tool_args_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            nonlocal attempts
            attempts += 1

            if tool_name_override is not None:
                tool_name = tool_name_override
                tool_args = tool_args_override or {}
            elif needs_decision:
                tool_name, tool_args = await self._decide(step, plan, result)
            else:
                tool_name = step.tool_name
                tool_args = step.tool_args

            result["tool_name"] = tool_name
            result["tool_args"] = tool_args

            if tool_name == "done":
                return {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "output": tool_args.get("summary", "Task complete"),
                }

            output = await self.tools.execute(tool_name, tool_args)

            if step.action in ("click", "fill", "navigate") and self.vision:
                try:
                    screenshot = await self._take_screenshot()
                    if screenshot:
                        verified, reasoning = await self.vision.verify_state(
                            screenshot, step.expected_result
                        )
                        if not verified:
                            self.logger.warning(f"Verification: {reasoning}")
                except Exception:
                    pass

            return {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "output": output,
            }

        async def execute_with_recovery(tool_name_override: Optional[str] = None,
                                        tool_args_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return await smart_retry(
                lambda: run_tool(tool_name_override, tool_args_override),
                logger=self.logger,
                max_attempts_by_category={
                    "TRANSIENT": step.max_retries + 1,
                    "UNKNOWN": step.max_retries + 1,
                    "PERMANENT": 1,
                },
            )

        try:
            execution = await execute_with_recovery()
        except Exception as e:
            if step.fallback_action:
                self.logger.info(f"Trying fallback: {step.fallback_action}")
                try:
                    execution = await execute_with_recovery(step.fallback_action, {})
                except Exception as fallback_error:
                    e = fallback_error
                    result["error"] = str(e)
                    result["retries"] = max(0, attempts - 1)
                    self.memory.add(MemoryEntry(
                        step_name=step.description,
                        action=step.action,
                        tool_used=result.get("tool_name"),
                        tool_args=result.get("tool_args", {}),
                        success=False,
                        error=str(e),
                    ))
                    self.logger.error(f"Step {step.id} exhausted retries: {e}")
                else:
                    result["success"] = True
                    result["output"] = execution["output"]
            else:
                result["error"] = str(e)
                result["retries"] = max(0, attempts - 1)
                self.memory.add(MemoryEntry(
                    step_name=step.description,
                    action=step.action,
                    tool_used=result.get("tool_name"),
                    tool_args=result.get("tool_args", {}),
                    success=False,
                    error=str(e),
                ))
                self.logger.error(f"Step {step.id} exhausted retries: {e}")
        else:
            result["success"] = True
            result["output"] = execution["output"]

        result["retries"] = max(0, attempts - 1)

        if result["success"]:
            self.memory.add(MemoryEntry(
                step_name=step.description,
                action=step.action,
                tool_used=result.get("tool_name"),
                tool_args=result.get("tool_args", {}),
                result=result.get("output"),
                success=True,
                selector_used=result.get("tool_args", {}).get("selector"),
            ))

        end = datetime.now()
        result["duration_ms"] = (end - start).total_seconds() * 1000
        self.logger.step_result(step.id, result["success"], result["duration_ms"])

        return result

    async def _decide(self, step: PlanStep, plan: Plan, last_result: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        context = self.memory.get_context_for_prompt(max_entries=10)

        system = """You are an RPA agent deciding what tool to call next.
Return JSON: {"tool_name": "...", "tool_args": {...}}

Available tools:
""" + "\n".join(f"- {t.name}: {t.description}" for t in self.tools.list())

        user = f"""Current step:
  ID: {step.id}
  Action: {step.action}
  Description: {step.description}
  Expected: {step.expected_result}

Task: {plan.task}

Recent history:
{context}

Previous step output: {json.dumps(last_result.get('output', '') if last_result else '', default=str)[:300]}

Which tool should I call? Return the tool name and arguments."""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            data = json.loads(response.choices[0].message.content)
            tool_name = data.get("tool_name", "done")
            tool_args = data.get("tool_args", {})

            self.logger.debug(f"Decided: {tool_name}({json.dumps(tool_args)})")
            return tool_name, tool_args

        except Exception as e:
            self.logger.warning(f"Decision LLM failed: {e} — returning done")
            return "done", {"summary": f"Could not decide: {e}", "status": "failed"}

    async def _take_screenshot(self) -> Optional[str]:
        if self.playwright:
            try:
                return await self.playwright.screenshot(name=f"agent_step_{self.memory._entry_counter}.png")
            except Exception:
                pass
        return None
