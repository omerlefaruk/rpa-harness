# Hook Taxonomy

Agent roles and skills declare lifecycle hooks as procedure markers. Hooks do not replace ActiveGraph lifecycle authority (EventStore + `AutomationApplication`).

## Hook IDs

| Hook | Description |
|---|---|
| `preflight` | Read AGENTS.md and relevant rules, confirm scope, identify constraints |
| `compliance` | Enforce boundaries, no secrets, no hardcoded values, no parallel runtime |
| `validation` | Run appropriate tests and validators (including OKF when docs change) |
| `reporting` | Summarize changes, tests, risks, and open questions |
| `failure` | Capture error context; prefer inspect/export evidence over assumptions |
| `perf-scout` | Note performance opportunities (advisory) |
| `refactor-scout` | Note safe refactor opportunities (advisory) |

## Requirements

1. Required hooks should be declared in skill frontmatter when the skill uses them
2. If a hook is not applicable, state why in the response
3. `perf-scout` and `refactor-scout` are advisory only
