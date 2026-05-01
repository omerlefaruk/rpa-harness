@./SKILL.md
@./docs/architecture.md
@./.agents/rules/01-core.md

# AI Agent Rules for rpa-harness

## Project Purpose

AI-assisted RPA automation harness. Describe a task, provide step-by-step instructions, input files, target apps/sites, and secret names → the system helps build, run, verify, debug, repair, and improve automations using a deterministic Python harness plus AI assistance.

## Core Principle

Build deterministic automation code that AI agents can inspect, generate, repair, and improve through evidence. Do not build uncontrolled autonomy.

## Project Context

- **Language**: Python 3.10+
- **Framework**: Playwright + pywinauto + OpenAI-compatible Vision + SQLite memory
- **Architecture**: Orchestrator → Drivers (Browser/Desktop/API) + Verification → AI Layer (Agent/Vision/Planner) + RPA Memory

## Required Workflow

For every task:
1. Open RPA Memory first: search for relevant prior sessions, selectors, failures, workflows, and decisions before planning or editing.
2. Inspect relevant files
3. Understand the requested automation
4. Identify type: browser, desktop, API, Excel/workflow, harness improvement, skill/rule/memory update
5. Create or update a plan
6. Make the smallest useful change
7. Add or update tests
8. Run verification commands
9. Produce final summary: files changed, commands run, test results, remaining risks

## Verification Rules

A workflow step is NOT successful because an action executed. It is successful ONLY when its success checks pass.

Every workflow step must include success checks. Examples: URL contains expected path, expected text visible, file exists, Excel cell updated, API response correct, desktop element reached expected state.

## Credential Rules

- Never hardcode credentials
- Never print secrets
- Never commit `.env`
- Never store raw secrets in logs, screenshots, memory, reports, workflow outputs, or generated examples
- Use secret names and environment variables only

## Mutation Protocol

Core harness, memory policy, credential policy, and `.agents/skills` are protected areas. Before editing: state why, reproduce failure, add test, apply smallest patch, run tests, summarize evidence.

Protected areas: `harness/core/`, `harness/orchestrator.py`, `harness/memory/`, `docs/mutation_protocol.md`, `docs/credential_policy.md`, `docs/memory_policy.md`, `AGENTS.md`, `.agents/rules/`, `.agents/skills/`

## Memory Rules

Memory stores evidence, not assumptions. Allowed: selector stats, error signatures, recovery outcomes, workflow history, reusable lessons. Disallowed: passwords, cookies, personal data, one-off guesses, unverified claims.

Before any task work, query RPA Memory using the 3-layer pattern: `GET /api/search` for compact matches, `GET /api/timeline` for surrounding context, and `POST /api/observations/batch` only for the specific details needed. If the RPA Memory service is unavailable, state that and continue only with current repo evidence unless the task explicitly requires memory.

## Browser Automation

Use Playwright. Selector priority: data-testid > role+name > label > placeholder > text > id > CSS > XPath. Coordinate fallback never unless explicitly last resort. On failure: screenshot, DOM snapshot, console/network logs, current URL, step id.

## Desktop Automation

Use Windows UIAutomation. Priority: automation_id > name+control_type > class_name+control_type > tree_path > image fallback. Coordinate last resort. Include window title and process name in evidence.

## Patch Rules

Do not make broad rewrites. Prefer small patches. Fixing failures: read failure report, identify step, classify (bad selector / timing / credentials / UI change / app down / business rule / harness bug), patch only required layer, re-run.

## Agent Decision Rules

### Create a test
- Place in `tests/browser/` (web) or `tests/desktop/` (desktop)
- Include `name`, `tags`, `setup()`, `run()`, `teardown()` — all async
- Use `self.step()` for every major action

### Create an RPA workflow
- Place in `tests/rpa/` or `workflows/`
- Extend `RPAWorkflow` with `setup()` → `get_records()` → `process_record()` → `on_mismatch()` → `teardown()`
- Use `config.variables` for paths (never hardcode)
- Tag with `["rpa", "excel"]` plus domain tags

### Run tests/workflows
- `python main.py --discover ./tests --run --report html`
- `python main.py --run-workflows --discover-wf ./tests/rpa`
- `python main.py --agent "task description" --headless`

### Delegate to subagents
- `explorer` (fast model) — file reading, info gathering
- `selector` (fast model) — browser reconnaissance, selector discovery
- `uia-tree` (fast model) — Windows UIA tree walking
- `planner` (powerful model) — task decomposition
- `memory` (fast model) — searching past sessions

## Code Style
- All lifecycle methods async: `setup()`, `run()`, `teardown()`, `process_record()`
- Type hints: `Optional[str]`, `dict`, `list`
- Dataclasses: `@dataclass` for config and result objects
- No `print()` in harness/: Use `HarnessLogger`
- Error handling: Catch in drivers, re-raise with context, never swallow silently

## Testing Rules
- Before committing: `python3 -m py_compile harness/*.py harness/**/*.py main.py`
- Never check in `reports/`, `runs/`, `screenshots/`, `data/*.xlsx`, `*.db`
- Never hardcode API keys or file paths

## Done Definition
A task is done only when: code implemented, tests added/updated, commands run, outputs reported, risks stated.
