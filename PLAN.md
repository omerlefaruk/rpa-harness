# RPA Harness — Complete Architecture Plan

## Overview

AI-powered RPA automation harness with Playwright (browser), Windows UIAutomation (desktop), API integrations, Excel-driven workflows, agentic AI loop, persistent memory, subagent dispatch, and web dashboard.

## Architecture Layers

### Layer 1: Python Harness (core automation engine)

```
harness/
├── orchestrator.py          # AutomationHarness: discover → run → report → serve
├── config.py                # @dataclass + env + YAML + model mapping
├── logger.py                # JSONL structured logger
│
├── drivers/                 # Abstraction layer
│   ├── base.py              # AbstractBaseDriver
│   ├── playwright.py        # Full Playwright async driver
│   ├── windows_ui.py        # pywinauto UIA Windows-only
│   └── api.py               # httpx REST driver
│
├── ai/                      # AI Layer
│   ├── agent.py             # Agent loop: plan → observe → decide → act → verify
│   ├── vision.py            # Vision engine (OpenAI-compatible)
│   ├── planner.py           # Task → step decomposition
│   ├── memory.py            # Agent short-term memory (step history)
│   └── tools.py             # Tool registry (function-calling schema)
│
├── memory/                  # Persistent memory (claude-mem pattern)
│   ├── engine.py            # RPAMemory main class
│   ├── database.py          # SQLite + FTS5 schema
│   ├── server.py            # FastAPI worker (:38777)
│   ├── hooks.py             # Lifecycle hook dispatcher
│   ├── compress.py          # AI summarization pipeline
│   ├── search.py            # 3-layer search (index → context → details)
│   └── inject.py            # Context injection formatting
│
├── rpa/                     # RPA-specific modules
│   ├── workflow.py          # RPAWorkflow (Excel-driven record loop)
│   ├── excel.py             # ExcelHandler (openpyxl)
│   ├── retry.py             # backoff, polling, circuit breaker
│   ├── queue.py             # Job queue + scheduling
│   └── office.py            # Outlook/Word/PDF integrations
│
├── resilience/              # Error handling
│   ├── errors.py            # Domain exception hierarchy
│   ├── healing.py           # Auto-heal selectors (ladder + AI)
│   └── recovery.py          # Recovery strategies
│
├── selectors/
│   └── strategies.py        # Selector priority ladder
│
└── reporting/
    ├── html_reporter.py     # Standalone HTML report
    ├── json_reporter.py     # JSON output
    └── dashboard.py         # FastAPI + Jinja2 web dashboard
```

### Layer 2: Subagent Classes (programmatic dispatch)

```
subagents/
├── base.py                  # BaseSubagent (LLM client + tool registry)
├── explorer.py              # File reading, codebase search, info gathering
├── selector.py              # Browser reconnaissance: navigate, inspect, discover
├── uia_tree.py              # Windows UIA tree walking + element naming
├── planner.py               # Task decomposition + dependency ordering
└── memory.py                # Memory search subagent
```

### Layer 3: .agents/ Configuration (AI coding tool dispatch)

```
.agents/
├── skills/                  # Agent Skills (agentskills.io spec)
│   ├── skill-creator/       # init_skill.py + package_skill.py
│   ├── playwright-automation/   # Reconnaissance-then-action pattern
│   ├── windows-ui-automation/   # UIA tree walking
│   ├── rpa-patterns/        # Retry/circuit breaker/polling
│   ├── selector-strategies/ # Priority ladder
│   ├── error-recovery/      # Exception hierarchy + fallback
│   ├── agent-delegation/    # Subagent routing rules
│   ├── excel-workflows/     # Excel-driven RPA patterns
│   ├── office-automations/  # Outlook/Word/PDF
│   └── memory-search/       # Memory search skill
│
├── rules/
│   ├── 00-role.md           # Agent role definition
│   ├── 01-core.md           # Core workflow
│   ├── 02-subagents.md      # Subagent routing matrix
│   ├── 03-model-mapping.md  # Task-type → model mapping
│   ├── 04-hooks.md          # Hook taxonomy
│   ├── 05-enforcement.md    # Enforcement + verification
│   └── 06-memory.md         # Memory system rules
│
└── config/
    └── agents.yaml          # Model assignments per subagent
```

## Subagent Routing Matrix

| Trigger Pattern | Subagent | Model | Tool Set | Returns |
|---|---|---|---|---|
| "read file", "find in code", "scan directory" | explorer | fast (gpt-4o-mini) | Read, Glob, Grep | {files, findings} |
| "find selectors", "inspect page", "get HTML" | selector | fast (gpt-4o-mini) | playwright-automation scripts | {selectors, elements, html} |
| "desktop element", "UIA tree", "windows control" | uia-tree | fast (gpt-4o-mini) | windows-ui-automation scripts | {tree, named_elements, ids} |
| "plan task", "decompose", "create workflow" | planner | powerful (gpt-4o) | planner.py | {steps, deps, risks} |
| "remember", "previous session", "selector cache" | memory | fast (gpt-4o-mini) | memory-search skill | {context, selectors, patterns} |
| "execute", "run workflow", "click", "type" | orchestrator | powerful (gpt-4o) | ALL drivers + tools | Full execution result |

## Memory System (claude-mem pattern)

### 5 Lifecycle Hooks
```
SessionStart → StepStart → PostStep → StepError → SessionEnd
```

### Database Schema
- `sessions` — workflow execution history
- `observations` — per-step captures (selector, result, timing, screenshots)
- `summaries` — AI-compressed session summaries with embeddings
- `selector_cache` — known-good selectors per URL pattern with validation stats
- `error_patterns` — failure signatures with recovery strategies

### 3-Layer Search
```
Layer 1: index (compact, ~50 tokens/result) → search()
Layer 2: context (timeline, ~200 tokens)        → context()
Layer 3: details (full fetch, ~500 tokens)      → fetch()
```

## Phase Plan

### Phase 1 — Foundation
- [ ] harness/config.py — @dataclass config + env + YAML + model mapping
- [ ] harness/logger.py — JSONL structured logger
- [ ] pyproject.toml — dependencies
- [ ] requirements.txt — pip deps
- [ ] config/default.yaml — default config template

### Phase 2 — Resilience
- [ ] harness/resilience/errors.py — domain exception hierarchy
- [ ] harness/resilience/healing.py — auto-heal selectors
- [ ] harness/resilience/recovery.py — recovery strategies
- [ ] harness/selectors/strategies.py — selector priority ladder

### Phase 3 — RPA Engine
- [ ] harness/rpa/excel.py — ExcelHandler
- [ ] harness/rpa/retry.py — backoff, polling, circuit breaker
- [ ] harness/rpa/workflow.py — RPAWorkflow base
- [ ] harness/rpa/queue.py — job queue + scheduling
- [ ] harness/rpa/office.py — Office integrations

### Phase 4 — Drivers
- [ ] harness/drivers/base.py — AbstractBaseDriver
- [ ] harness/drivers/playwright.py — Playwright async driver
- [ ] harness/drivers/windows_ui.py — Windows UIA driver
- [ ] harness/drivers/api.py — httpx REST driver

### Phase 5 — AI Layer
- [ ] harness/ai/vision.py — Vision engine
- [ ] harness/ai/tools.py — Tool registry
- [ ] harness/ai/planner.py — Task planner
- [ ] harness/ai/memory.py — Agent short-term memory
- [ ] harness/ai/agent.py — Full agent loop

### Phase 6 — Memory System
- [ ] harness/memory/database.py — SQLite schema
- [ ] harness/memory/engine.py — RPAMemory class
- [ ] harness/memory/hooks.py — Lifecycle hooks
- [ ] harness/memory/compress.py — AI summarization
- [ ] harness/memory/search.py — 3-layer search
- [ ] harness/memory/inject.py — Context injection
- [ ] harness/memory/server.py — FastAPI worker

### Phase 7 — Reporting
- [ ] harness/reporting/json_reporter.py
- [ ] harness/reporting/html_reporter.py
- [ ] harness/reporting/dashboard.py — FastAPI + Jinja2

### Phase 8 — Orchestrator + CLI
- [ ] harness/__init__.py — package exports
- [ ] harness/orchestrator.py — AutomationHarness
- [ ] harness/test_case.py — AutomationTestCase
- [ ] main.py — CLI entrypoint
- [ ] conftest.py — Pytest fixtures

### Phase 9 — Subagents
- [ ] subagents/base.py
- [ ] subagents/explorer.py
- [ ] subagents/selector.py
- [ ] subagents/uia_tree.py
- [ ] subagents/planner.py
- [ ] subagents/memory.py

### Phase 10 — .agents/ Governance
- [ ] .agents/rules/*.md — 7 rule files
- [ ] .agents/config/agents.yaml — model assignments
- [ ] .agents/skills/*/SKILL.md — 10 skill definitions
- [ ] AGENTS.md — root agent rules
- [ ] SKILL.md — top-level harness skill

### Phase 11 — Tests + Examples
- [ ] tests/browser/ — example browser tests
- [ ] tests/desktop/ — example desktop tests
- [ ] tests/api/ — example API tests
- [ ] tests/rpa/ — example RPA workflows
- [ ] workflows/examples/ — example workflow definitions

## Patterns Carried Forward from automation-harness/
- `step()` / `step_done()` pairing for structured tracing
- `on_mismatch()` callback pattern in RPAWorkflow
- Auto-healing with fallback variation ladder
- `config.variables` for path/credential injection
- Tag-based test/workflow filtering
- Discover → run → report orchestrator pattern

## Patterns Adapted from CasareRPA
- Domain exception hierarchy with error codes
- Retry with exponential backoff + circuit breaker state machine
- Selector priority ladder (data-testid > aria-label > name > id > class)
- Page Object pattern for browser testing
- Hook taxonomy (preflight, compliance, validation, reporting, failure)
- Progressive disclosure design for skills

## Patterns Adapted from claude-mem
- 5 lifecycle hooks (SessionStart → StepStart → PostStep → StepError → SessionEnd)
- SQLite + FTS5 for observability storage
- 3-layer progressive disclosure search (index → context → details)
- AI compression pipeline for session summaries
- Selector cache with validation tracking
- Error pattern learning with recovery strategy tracking
