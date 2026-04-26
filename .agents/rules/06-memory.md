# Memory System Rules

Adapted from claude-mem architecture.

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

1. **Layer 1 — index**: `memory/search?q=query&type=all&limit=10` → compact results (~50 tokens each)
2. **Layer 2 — context**: `memory/context/{obs_id}?window=5` → timeline around match (~200 tokens)
3. **Layer 3 — details**: POST `/memory/observations` with IDs → full data (~500 tokens each)

## When to Search Memory

- Before starting any browser or desktop interaction (cache selectors)
- Before retrying a failed step (check error patterns)
- When planning a workflow (check similar past sessions)

## When to Store to Memory

- After every successful step (selector used, timing)
- After every failed step (error pattern, screenshot path)
- At session end (complete summary)
