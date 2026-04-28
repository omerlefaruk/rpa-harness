# Memory System Rules

RPA Memory is the first context source for agents working in this repo.

## Lifecycle

```
SessionStart → StepStart → PostStep → StepError → SessionEnd
```

## What Gets Stored

| Event | Data Captured |
|---|---|
| SessionStart | workflow_name, task_description, config_snapshot |
| PostStep | step_name, action, tool_used, selector, success, duration, screenshot |
| StepError | error_message, error_category, recovery strategy attempted |
| SessionEnd | status, total_steps, successful_steps, failed_steps, duration |

## Search Pattern (3-Layer Progressive Disclosure)

1. **Layer 1 — index**: `GET /api/search?query=...&type=all&limit=10` → compact results with observation IDs.
2. **Layer 2 — context**: `GET /api/timeline?anchor=<obs_id>&depth_before=3&depth_after=3` → surrounding context around the match.
3. **Layer 3 — details**: `POST /api/observations/batch` with selected IDs → full observation data only when needed.

## When to Search Memory

- Before every task, before planning, and before editing code
- Before starting any browser or desktop interaction (cache selectors)
- Before retrying a failed step (check error patterns)
- When planning a workflow (check similar past sessions)
- When changing harness architecture, memory behavior, credentials, verification, or agent rules

If RPA Memory is unavailable, state the outage clearly and continue from current repo evidence unless the task explicitly depends on memory.

## When to Store to Memory

- After every successful step (selector used, timing)
- After every failed step (error pattern, screenshot path)
- At session end (complete summary)
