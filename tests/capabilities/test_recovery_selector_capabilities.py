"""Capability characterization for selectors, recovery, and mocked agent tools."""

import json
from pathlib import Path

import pytest
import yaml

from harness.ai.agent import RPAAgent
from harness.ai.planner import Plan, PlanStep
from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.reporting.failure_report import FailureReport
from harness.resilience.errors import ValidationError
from harness.resilience.recovery import CircuitBreaker, CircuitBreakerOpenError, smart_retry
from harness.rpa.yaml_runner import YamlWorkflowRunner
from harness.selectors.strategies import (
    SELECTOR_PRIORITY,
    get_healing_ladder,
    is_dynamic_selector,
    score_selector,
)


class SequencedResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = json.dumps({"status": status_code})
        self.url = "http://127.0.0.1:8765/retry"
        self.headers = {"content-type": "application/json"}

    def json(self):
        return json.loads(self.text)


class SequencedAPIDriver:
    def __init__(self, statuses: list[int]):
        self.statuses = list(statuses)
        self.calls = 0

    async def get(self, path, params=None, headers=None):
        self.calls += 1
        status = self.statuses.pop(0) if self.statuses else 200
        return SequencedResponse(status)

    async def close(self):
        return None


def _write_yaml(tmp_path: Path, workflow: dict) -> Path:
    path = tmp_path / f"{workflow['id']}.yaml"
    path.write_text(yaml.safe_dump(workflow))
    return path


async def _run_yaml_with_api(tmp_path: Path, workflow: dict, fake: SequencedAPIDriver):
    runner = YamlWorkflowRunner(HarnessConfig(headless=True, enable_vision=False))
    runner.failure = FailureReport(str(tmp_path / "runs"))

    async def get_fake_api():
        runner._drivers["api"] = fake
        return fake

    runner._get_api_driver = get_fake_api
    return await runner.run(str(_write_yaml(tmp_path, workflow)))


def test_selector_priority_identifies_stable_and_dynamic_selectors():
    assert SELECTOR_PRIORITY[0][0] == "data-testid"
    assert is_dynamic_selector("div:nth-child(3)")
    assert is_dynamic_selector(".css-abc123def")
    assert not is_dynamic_selector("[data-testid='submit']")


def test_healing_ladder_produces_stable_alternatives_before_xpath_fallbacks():
    ladder = get_healing_ladder("#submit")

    assert "[data-testid='submit']" in ladder
    assert "[name='submit']" in ladder
    assert ladder.index("[data-testid='submit']") < ladder.index("//*[contains(@id, '#submit')]")


def test_dynamic_selectors_score_worse_than_stable_selectors():
    stable = score_selector("[data-testid='submit']")
    nth_child = score_selector("div:nth-child(3)")
    generated_class = score_selector(".css-abc123def")

    assert stable > nth_child
    assert stable > generated_class


@pytest.mark.asyncio
async def test_yaml_retry_recovery_reexecutes_transient_api_check_failure(tmp_path):
    fake = SequencedAPIDriver([500, 200])
    workflow = {
        "id": "yaml_retry_recovery",
        "name": "YAML Retry Recovery",
        "version": "1.0",
        "type": "api",
        "steps": [
            {
                "id": "read_with_retry",
                "action": {"type": "api.get", "url": "http://127.0.0.1:8765/retry"},
                "success_check": [{"type": "status_code", "value": 200}],
                "recovery": [{"type": "retry", "max_attempts": 2}],
            }
        ],
    }

    result = await _run_yaml_with_api(tmp_path, workflow, fake)

    assert result["status"] == "passed"
    assert result["steps"][0]["attempts"] == 2
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_yaml_wait_recovery_reexecutes_api_check_after_delay(tmp_path):
    fake = SequencedAPIDriver([500, 200])
    workflow = {
        "id": "yaml_wait_recovery",
        "name": "YAML Wait Recovery",
        "version": "1.0",
        "type": "api",
        "steps": [
            {
                "id": "read_after_wait",
                "action": {"type": "api.get", "url": "http://127.0.0.1:8765/retry"},
                "success_check": [{"type": "status_code", "value": 200}],
                "recovery": [{"type": "wait", "ms": 1}],
            }
        ],
    }

    result = await _run_yaml_with_api(tmp_path, workflow, fake)

    assert result["status"] == "passed"
    assert result["steps"][0]["attempts"] == 2
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_smart_retry_retries_transient_but_not_permanent_errors():
    transient_calls = []

    async def transient_operation():
        transient_calls.append(1)
        if len(transient_calls) == 1:
            raise TimeoutError("timed out")
        return "ok"

    permanent_calls = []

    async def permanent_operation():
        permanent_calls.append(1)
        raise ValidationError("invalid selector")

    assert await smart_retry(transient_operation) == "ok"
    with pytest.raises(ValidationError):
        await smart_retry(permanent_operation)

    assert len(transient_calls) == 2
    assert len(permanent_calls) == 1


@pytest.mark.asyncio
async def test_circuit_breaker_open_state_is_deterministic():
    breaker = CircuitBreaker(failure_threshold=2, timeout_ms=1000)

    async def fail():
        raise RuntimeError("down")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(fail)


class FlakyTools:
    def __init__(self):
        self.calls = 0

    async def execute(self, name, arguments):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("temporary tool failure")
        return {"tool": name, "arguments": arguments}


class FakeNotifier:
    def __init__(self):
        self.events = []

    async def question(self, question: str, *, context: dict = None):
        self.events.append(("question", question, context))

    async def failure(self, message: str, *, context: dict = None, topic: str = "failures"):
        self.events.append(("failure", message, context))

    async def frustration(self, message: str, *, context: dict = None):
        self.events.append(("frustration", message, context))

@pytest.mark.asyncio
async def test_rpa_agent_step_execution_uses_mocked_tools_and_retries(monkeypatch):
    monkeypatch.setattr(HarnessLogger, "_setup_jsonl", lambda self, path: setattr(self, "_jsonl_path", path))

    agent = RPAAgent(config=HarnessConfig(enable_vision=False, agent_max_steps=2))
    tools = FlakyTools()
    agent.tools = tools
    notifier = FakeNotifier()
    agent.notifier = notifier
    step = PlanStep(
        id=1,
        action="click",
        description="Click deterministic button",
        tool_name="browser_click",
        tool_args={"selector": "[data-testid='submit']"},
        expected_result="success text visible",
        max_retries=1,
    )
    plan = Plan(task="click button", steps=[step])

    result = await agent._execute_step(step, plan)

    assert result["success"] is True
    assert result["retries"] == 1
    assert tools.calls == 2
    assert (
        "frustration",
        "I recovered this agent step after retrying it.",
        {
            "step": "Click deterministic button",
            "tool": "browser_click",
            "retries": 1,
        },
    ) in notifier.events
