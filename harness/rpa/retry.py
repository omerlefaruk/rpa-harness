"""
RPA resilience patterns: retry, polling, circuit breaker.
Re-exported from harness.resilience.recovery for RPA-specific convenience.
"""

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

__all__ = [
    "retry_with_backoff",
    "poll_for_condition",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "RecoveryStrategy",
    "execute_with_fallback",
    "smart_retry",
]
