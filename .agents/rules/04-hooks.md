# Hook Taxonomy

All agent roles and skills must declare required hooks.

## Hook IDs

| Hook | Description |
|---|---|
| `preflight` | Read AGENTS.md and relevant rules, confirm scope, identify constraints |
| `compliance` | Enforce boundaries, async rules, no secrets, no hardcoded values |
| `validation` | Run appropriate tests, validators, linters, type checks |
| `reporting` | Summarize changes, tests, risks, and open questions |
| `failure` | Capture error context and propose next step or fallback |
| `perf-scout` | Note performance optimization opportunities (advisory) |
| `refactor-scout` | Note safe refactor opportunities (advisory) |

## Requirements

1. Required hooks must be declared in SKILL.md frontmatter
2. If a hook is not applicable, state why in the response
3. `perf-scout` and `refactor-scout` are advisory only
