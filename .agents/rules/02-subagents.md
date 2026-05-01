# Subagent Routing Matrix

## When to Dispatch Subagents

Use Task tool with appropriate subagent_type for efficient parallel execution.

| Trigger Pattern | Subagent | Model | Max Parallel |
|---|---|---|---|
| "read file", "find in code", "scan directory", "check config", "gather info" | explorer | fast (gpt-4o-mini) | 4 |
| "find selectors", "inspect page", "HTML snapshot", "DOM", "screenshot page" | selector | fast (gpt-4o-mini) | 2 |
| "desktop element", "UIA tree", "windows control", "app window", "dump tree" | uia-tree | fast (gpt-4o-mini) | 1 |
| "plan task", "decompose", "break down", "create workflow from" | planner | powerful (gpt-4o) | 1 |
| "remember", "previous session", "selector cache", "error history", "past runs" | memory | fast (gpt-4o-mini) | 2 |
| "execute", "click", "type", "navigate", "run workflow", "run agent" | orchestrator | powerful (gpt-4o) | 1 |

## Dispatch Rules

1. **Parallel when independent**: Explorer + Selector can run together. Explorer + Planner can run together.
2. **Sequential when dependent**: Selector must complete before Planner uses its results.
3. **Respect max_parallel**: Never exceed configured parallel limits.
4. **Timeout management**: Selector and UIA-tree get 60s, Explorer gets 30s, Planner gets 120s.

## Orchestrator Dispatch Flow

```
User task received
  │
  ├─ PARALLEL: Explorer reads files/config + Selector navigates + discovers
  │
  ├─ Planner (with Explorer + Selector results) → steps
  │
  └─ Orchestrator executes steps
      ├─ Per step: Memory search for cached selectors
      ├─ Per step: Selector validates current page selectors
      └─ Per step: Capture observation to memory
```
