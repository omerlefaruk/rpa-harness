---
name: agent-delegation
description: >
  Subagent routing rules for RPA Harness. When to dispatch
  explorer, selector, uia-tree, planner, or memory subagents.
  Model routing for fast vs powerful tasks.
  Use when planning complex multi-step automation tasks.
hooks: "preflight, compliance, validation, reporting"
---

# Agent Delegation

## Subagent Dispatch Rules

See `.agents/rules/02-subagents.md` for the full routing matrix.

## Pipeline Pattern

For complex tasks, use pipelined subagent dispatch:

```
1. Explorer (fast) + Selector (fast) → parallel reconnaissance
2. Planner (powerful) → decompose with gathered context
3. Orchestrator (powerful) → execute steps
4. Memory (fast) → capture and search between steps
```

## Parallel Dispatch Example

```python
results = await asyncio.gather(
    dispatch_explorer("read all Excel files and config"),
    dispatch_selector("navigate to target URL and discover selectors"),
)
```
