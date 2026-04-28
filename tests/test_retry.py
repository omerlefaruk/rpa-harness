"""Tests for retry and recovery."""
import asyncio
from dataclasses import dataclass

import pytest

from harness.ai.agent import RPAAgent
from harness.ai.planner import Plan, PlanStep
from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.resilience.errors import ValidationError
from harness.resilience.recovery import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    RecoveryStrategy,
    execute_with_fallback,
    poll_for_condition,
    retry_with_backoff,
    smart_retry,
)
from harness.rpa.workflow import RPAWorkflow


def run(coro):
    return asyncio.run(coro)


def test_recovery_strategy_enum():
    assert RecoveryStrategy.RETRY.value == "retry"
    assert RecoveryStrategy.ABORT.value == "abort"


def test_circuit_state_enum():
    assert CircuitState.CLOSED.value == "closed"
    assert CircuitState.OPEN.value == "open"


def test_retry_succeeds_first_attempt():
    calls = []

    async def op():
        calls.append(1)
        return "ok"

    result = run(retry_with_backoff(op, max_attempts=3, base_delay_ms=10, jitter=False))
    assert result == "ok"
    assert len(calls) == 1


def test_retry_eventually_succeeds():
    calls = []

    async def op():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("transient")
        return "ok"

    result = run(retry_with_backoff(op, max_attempts=3, base_delay_ms=10, jitter=False))
    assert result == "ok"
    assert len(calls) == 2


def test_retry_exhausts():
    async def op():
        raise ValueError("persistent")

    with pytest.raises(ValueError):
        run(retry_with_backoff(op, max_attempts=2, base_delay_ms=10, jitter=False))


def test_polling_succeeds():
    results = [False, False, True]

    async def condition():
        return results.pop(0)

    result = run(poll_for_condition(condition, timeout_ms=5000, interval_ms=10))
    assert result is True


def test_polling_timeout():
    async def condition():
        return False

    with pytest.raises(TimeoutError):
        run(poll_for_condition(condition, timeout_ms=100, interval_ms=10))


def test_fallback():
    async def primary():
        raise ValueError("primary failed")

    async def fallback():
        return "fallback_value"

    result = run(execute_with_fallback(primary, fallback))
    assert result == "fallback_value"


def test_fallback_when_primary_succeeds():
    async def primary():
        return "primary_value"

    async def fallback():
        return "fallback_value"

    result = run(execute_with_fallback(primary, fallback))
    assert result == "primary_value"


def test_circuit_breaker_opens():
    cb = CircuitBreaker(failure_threshold=2, timeout_ms=10)

    async def failing_op():
        raise ValueError("fail")

    for _ in range(2):
        with pytest.raises(ValueError):
            run(cb.call(failing_op))

    assert cb._state == CircuitState.OPEN
    assert cb._failures >= cb.failure_threshold


def test_circuit_breaker_reset():
    cb = CircuitBreaker(failure_threshold=2, timeout_ms=10)

    async def fail_then_succeed():
        if cb._failures < 2:
            raise ValueError("fail")
        return "ok"

    for _ in range(2):
        with pytest.raises(ValueError):
            run(cb.call(fail_then_succeed))

    asyncio.run(asyncio.sleep(0.02))
    run(cb.call(lambda: asyncio.sleep(0)))
    assert cb._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)


def test_smart_retry_transient():
    calls = []

    async def op():
        calls.append(1)
        if len(calls) < 2:
            raise TimeoutError("transient")
        return "ok"

    result = run(smart_retry(op, "TRANSIENT"))
    assert result == "ok"


def test_smart_retry_auto_classifies_transient():
    calls = []

    async def op():
        calls.append(1)
        if len(calls) < 2:
            raise TimeoutError("timed out")
        return "ok"

    result = run(smart_retry(op))
    assert result == "ok"
    assert len(calls) == 2


def test_smart_retry_does_not_retry_permanent_error():
    calls = []

    async def op():
        calls.append(1)
        raise ValidationError("invalid selector")

    with pytest.raises(ValidationError):
        run(smart_retry(op))

    assert len(calls) == 1


class _RetryingWorkflow(RPAWorkflow):
    name = "retrying-workflow"

    def __init__(self):
        super().__init__()
        self.calls = 0

    def get_records(self):
        return iter([])

    async def process_record(self, record: dict) -> dict:
        self.calls += 1
        if self.calls < 2:
            return {"status": "retry", "reason": "temporary"}
        return {"status": "passed"}


def test_workflow_process_with_retry_uses_shared_recovery():
    workflow = _RetryingWorkflow()
    result = run(workflow._process_with_retry({"id": 1}))

    assert result["status"] == "passed"
    assert workflow.calls == 2
    assert workflow.result.retried_records == 1


class _FlakyTools:
    def __init__(self):
        self.calls = 0

    async def execute(self, name, arguments):
        self.calls += 1
        if self.calls < 2:
            raise TimeoutError("temporary timeout")
        return {"ok": True, "name": name, "arguments": arguments}


def test_agent_step_uses_shared_recovery_for_transient_errors(monkeypatch):
    @dataclass
    class MemoryEntryStub:
        step_name: str
        action: str
        tool_used: str = ""
        tool_args: dict = None
        result: object = None
        success: bool = False
        selector_used: object = None
        error: str = ""

    monkeypatch.setattr(HarnessLogger, "_setup_jsonl", lambda self, path: setattr(self, "_jsonl_path", path))
    monkeypatch.setattr("harness.ai.agent.MemoryEntry", MemoryEntryStub)
    agent = RPAAgent(config=HarnessConfig(enable_vision=False))
    tools = _FlakyTools()
    agent.tools = tools
    agent.memory = type("MemoryStub", (), {"add": lambda self, entry: None})()

    step = PlanStep(
        id=1,
        action="click",
        description="Click target",
        tool_name="browser_click",
        tool_args={"selector": "#submit"},
        expected_result="clicked",
        max_retries=1,
    )
    plan = Plan(task="click button", steps=[step])

    result = run(agent._execute_step(step, plan))

    assert result["success"] is True
    assert result["retries"] == 1
    assert tools.calls == 2
