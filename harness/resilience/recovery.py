"""
Recovery strategies for resilient RPA automation.
Includes retry with backoff, polling, circuit breaker, and graceful degradation.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, TypeVar

from harness.logger import HarnessLogger
from harness.resilience.errors import classify_error

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    timeout_ms: int = 60000
    half_open_max_attempts: int = 1
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_attempts: int = field(default=0, init=False)
    _logger: Optional[HarnessLogger] = field(default=None, init=False)

    def __post_init__(self):
        self._logger = HarnessLogger("circuit-breaker")

    async def call(self, operation: Callable[[], Awaitable[T]], fallback: Optional[Callable[[], Awaitable[T]]] = None) -> T:
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._half_open_attempts = 0
                self._logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                if fallback:
                    self._logger.warning("Circuit OPEN — using fallback")
                    return await fallback()
                raise CircuitBreakerOpenError(
                    f"Circuit is OPEN. Retry after {self.timeout_ms}ms"
                )

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_attempts >= self.half_open_max_attempts:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                raise CircuitBreakerOpenError("Circuit HALF_OPEN limit exceeded")

        try:
            result = await operation()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if fallback:
                self._logger.warning(f"Operation failed: {e} — using fallback")
                return await fallback()
            raise

    def _on_success(self):
        self._failures = 0
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._logger.info("Circuit breaker → CLOSED (recovered)")

    def _on_failure(self):
        self._failures += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_attempts += 1
        if self._failures >= self.failure_threshold and self._state == CircuitState.CLOSED:
            self._state = CircuitState.OPEN
            self._logger.warning(f"Circuit breaker → OPEN ({self._failures} failures)")

    def _should_attempt_reset(self) -> bool:
        return (time.monotonic() - self._last_failure_time) > (self.timeout_ms / 1000)


class CircuitBreakerOpenError(Exception):
    pass


async def retry_with_backoff(
    operation: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
    jitter: bool = True,
    logger: Optional[HarnessLogger] = None,
) -> T:
    log = logger or HarnessLogger("retry")
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as e:
            last_exception = e
            if attempt == max_attempts:
                log.error(f"All {max_attempts} attempts failed: {e}")
                raise

            delay = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
            if jitter:
                delay = delay * (0.5 + random.random())

            log.warning(f"Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.0f}ms")
            await asyncio.sleep(delay / 1000)

    raise last_exception


async def poll_for_condition(
    condition: Callable[[], Awaitable[bool]],
    timeout_ms: int = 30000,
    interval_ms: int = 500,
    description: str = "",
    logger: Optional[HarnessLogger] = None,
) -> bool:
    log = logger or HarnessLogger("polling")
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        try:
            if await condition():
                return True
        except Exception:
            pass
        await asyncio.sleep(interval_ms / 1000)

    msg = f"Condition '{description or 'unnamed'}' not met within {timeout_ms}ms"
    log.warning(msg)
    raise TimeoutError(msg)


async def execute_with_fallback(
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]],
    fallback_label: str = "primary failed",
    logger: Optional[HarnessLogger] = None,
) -> T:
    log = logger or HarnessLogger("fallback")
    try:
        return await primary()
    except Exception as e:
        log.warning(f"Primary operation failed: {e}. Falling back: {fallback_label}")
        return await fallback()


class RecoveryStrategy(Enum):
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ABORT = "abort"
    ESCALATE = "escalate"


async def smart_retry(
    operation: Callable[[], Awaitable[T]],
    error_category: Optional[str] = None,
    logger: Optional[HarnessLogger] = None,
    max_attempts_by_category: Optional[dict[str, int]] = None,
) -> T:
    log = logger or HarnessLogger("smart-retry")

    strategies = {
        "TRANSIENT": (3, 1000),
        "UNKNOWN": (2, 2000),
        "PERMANENT": (1, 0),
    }

    if max_attempts_by_category:
        strategies = {
            category: (max_attempts_by_category.get(category, attempts), delay)
            for category, (attempts, delay) in strategies.items()
        }

    initial_exception: Optional[Exception] = None
    if error_category is None:
        try:
            return await operation()
        except Exception as e:
            initial_exception = e
            error_category = classify_error(e)
            log.warning(f"Detected {error_category} error: {e}")

    max_attempts, base_delay = strategies.get(error_category, (1, 0))

    if error_category == "PERMANENT":
        log.warning("Permanent error detected — not retrying")
        if initial_exception is not None:
            raise initial_exception
        return await operation()

    remaining_attempts = max_attempts - 1 if initial_exception is not None else max_attempts
    if remaining_attempts <= 0:
        if initial_exception is not None:
            raise initial_exception
        return await operation()

    return await retry_with_backoff(
        operation,
        max_attempts=remaining_attempts,
        base_delay_ms=base_delay,
        logger=log,
    )
