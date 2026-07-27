# ADR-0002: Skills are not enforcement

## Status

Accepted — 2026-07-27

## Context

Agent skills and rules are useful playbooks, but safety (verification, redaction, allowlists, retry, repair admission, budgets) must not depend on model compliance. Research: `docs/research/code-vs-skill-boundary.md`.

## Decision

**Code enforces; skills guide.** Validation, capability ports, verification after action, secret redaction, write at-most-once, repair fork admission, and MCP tool allowlists live in executable code (`harness.automation`, security, reporting, agent package). Skills may summarize contracts and teach the agent loop; they must never be the only place a safety rule exists. When prose and code disagree, code wins until docs/skills are fixed.

## Consequences

- Canonical skill `.agents/skills/rpa-harness-automation-builder` is procedure-only.
- Thin `.agents/rules/*` point at docs and code rather than duplicating catalogs.
- Selector ladders in skills/docs must match `harness.automation.capabilities`.
- Self-improvement cannot move enforcement into prompts.
