# Architecture — RPA Harness

## Overview

Local-first AI-assisted RPA automation harness. Describe a task or provide step-by-step instructions, input files, and secret names → the system helps build, run, debug, repair, and improve automations.

YAML workflows are the only supported runtime. Operators use terminal commands and run artifacts. Run artifacts are the source of truth. No dashboard, React frontend, SQLite observability DB, class workflow runtime, local subagent framework, Office/PDF layer, or job queue is part of the core.

## Layers

```
.agents/          ← Agent governance (rules, skills)
docs/             ← Contracts and policies
harness/          ← Deterministic Python runner
  core/           ← Session, step, result, evidence
  drivers/        ← Playwright, Windows UIA, API
  verification/   ← Success checks and contracts
  resilience/     ← Errors and recovery helpers
  selectors/      ← Priority ladder and repair helpers
  rpa/            ← YAML runner, schema, ledger, Excel helpers
  ai/             ← Agent loop, vision, planner, tools
  reporting/      ← HTML, JSON, failure reports
tools/            ← CLI utilities (inspect, analyze, patch)
projects/         ← Real workflow projects: workflow YAML, config, tests, README
runs/             ← Run artifacts per execution
workflows/        ← Shared YAML examples and capability fixtures
tests/            ← pytest test suite
config/           ← Shared default config template
```

## Execution Flow

```
User request → YAML workflow under projects/<project>/workflows/main.yaml
  → python main.py --audit-workflow / --run-yaml
  → deterministic step execution with verification
  → success checks per step
  → run artifacts under runs/<run_id>/
  → operator inspects with --runs-list / --runs-show / --logs-show / --report-open
```

## Safety Boundaries

- Runtime LLM: allowed for planning, diagnosis, summarization, selector healing, report analysis
- Runtime LLM: NEVER directly executes destructive business actions without workflow approval gates
- Core harness: protected, requires mutation protocol to edit
- Credentials: never in code, logs, screenshots, or reports
- Self-improvement: requires reproduced failure + root cause + passing tests
