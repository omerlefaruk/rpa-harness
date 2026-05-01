---
name: error-recovery
description: >
  RPA error handling patterns. Domain exception hierarchy,
  retry strategies, fallback patterns, error classification.
  Use when handling errors in RPA workflows or implementing
  resilient automation with retry and recovery.
hooks: "preflight, compliance, validation, reporting"
---

# Error Recovery

## Exception Hierarchy

| Exception | Code | Category |
|-----------|------|----------|
| TimeoutError | TIMEOUT | TRANSIENT |
| ElementNotFoundError | ELEMENT_NOT_FOUND | TRANSIENT |
| ElementStaleError | ELEMENT_STALE | TRANSIENT |
| ConnectionTimeoutError | CONNECTION_TIMEOUT | TRANSIENT |
| NetworkError | NETWORK_ERROR | TRANSIENT |
| SelectorInvalidError | SELECTOR_INVALID | PERMANENT |
| AuthenticationError | AUTHENTICATION_ERROR | PERMANENT |
| FileNotFoundError_ | FILE_NOT_FOUND | PERMANENT |

## Recovery Strategies

| Strategy | When to Use |
|----------|-------------|
| RETRY | Transient errors (timeout, stale, network) |
| SKIP | Non-critical operations |
| FALLBACK | Alternative value/path available |
| ABORT | Critical error, cannot continue |
| ESCALATE | Max retries exceeded |

## Usage

```python
from harness.resilience import retry_with_backoff, CircuitBreaker

await retry_with_backoff(
    lambda: driver.click("#unstable"),
    max_attempts=3,
    base_delay_ms=1000,
    jitter=True,
)
```
