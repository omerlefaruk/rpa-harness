"""Tests for retry and recovery."""
import asyncio
import pytest
from harness.resilience.recovery import (
    retry_with_backoff,
    poll_for_condition,
    CircuitBreaker,
    CircuitBreakerOpenError,
    execute_with_fallback,
    smart_retry,
    RecoveryStrategy,
    CircuitState,
)


def test_recovery_strategy_enum():
    assert RecoveryStrategy.RETRY.value == "retry"
    assert RecoveryStrategy.ABORT.value == "abort"


def test_circuit_state_enum():
    assert CircuitState.CLOSED.value == "closed"
    assert CircuitState.OPEN.value == "open"


@pytest.mark.asyncio
async def test_retry_succeeds_first_attempt():
    calls = []

    async def op():
        calls.append(1)
        return "ok"

    result = await retry_with_backoff(op, max_attempts=3, base_delay_ms=10, jitter=False)
    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_eventually_succeeds():
    calls = []

    async def op():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("transient")
        return "ok"

    result = await retry_with_backoff(op, max_attempts=3, base_delay_ms=10, jitter=False)
    assert result == "ok"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_retry_exhausts():
    async def op():
        raise ValueError("persistent")

    with pytest.raises(ValueError):
        await retry_with_backoff(op, max_attempts=2, base_delay_ms=10, jitter=False)


@pytest.mark.asyncio
async def test_polling_succeeds():
    results = [False, False, True]

    async def condition():
        return results.pop(0)

    result = await poll_for_condition(condition, timeout_ms=5000, interval_ms=10)
    assert result is True


@pytest.mark.asyncio
async def test_polling_timeout():
    async def condition():
        return False

    with pytest.raises(TimeoutError):
        await poll_for_condition(condition, timeout_ms=100, interval_ms=10)


@pytest.mark.asyncio
async def test_fallback():
    async def primary():
        raise ValueError("primary failed")

    async def fallback():
        return "fallback_value"

    result = await execute_with_fallback(primary, fallback)
    assert result == "fallback_value"


@pytest.mark.asyncio
async def test_fallback_when_primary_succeeds():
    async def primary():
        return "primary_value"

    async def fallback():
        return "fallback_value"

    result = await execute_with_fallback(primary, fallback)
    assert result == "primary_value"


@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    cb = CircuitBreaker(failure_threshold=2, timeout_ms=10)

    async def failing_op():
        raise ValueError("fail")

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(failing_op)

    assert cb._state == CircuitState.OPEN
    assert cb._failures >= cb.failure_threshold


@pytest.mark.asyncio
async def test_circuit_breaker_reset():
    cb = CircuitBreaker(failure_threshold=2, timeout_ms=10)

    async def fail_then_succeed():
        if cb._failures < 2:
            raise ValueError("fail")
        return "ok"

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(fail_then_succeed)

    # Wait for timeout
    await asyncio.sleep(0.02)
    result = await cb.call(lambda: asyncio.sleep(0))
    assert cb._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED)


@pytest.mark.asyncio
async def test_smart_retry_transient():
    calls = []

    async def op():
        calls.append(1)
        if len(calls) < 2:
            raise TimeoutError("transient")
        return "ok"

    result = await smart_retry(op, "TRANSIENT")
    assert result == "ok"
