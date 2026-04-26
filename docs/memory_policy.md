# Memory Policy

## Purpose

Memory stores evidence, not assumptions.

## Memory Categories

| Category | Contents | Lifetime |
|----------|----------|----------|
| **runtime** | Logs, screenshots, traces, raw observations | Per-session, archival |
| **operational** | Selector success/failure stats, recovery stats, error patterns | Across sessions, stats decay |
| **knowledge** | Stable reusable lessons and skills | Permanent, evidence-gated |

## Allowed Memory

- selector success/failure stats with URL patterns
- error signatures with recovery strategy outcomes
- summarized workflow history
- stable reusable lessons after repeated evidence

## Disallowed Memory

- raw passwords
- session cookies
- personal data unless explicitly required
- one-off guesses
- unverified selector claims
- screenshots containing secrets unless redacted

## Knowledge Gate

Only stable evidence becomes knowledge memory.

A lesson qualifies as knowledge when:
1. It has been observed at least 3 times across different runs
2. It can be stated as a deterministic rule
3. It has been verified by a test or reproducible run
4. It does not contain secrets or private data
