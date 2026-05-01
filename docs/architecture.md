# Architecture — RPA Harness

## Overview

Local-first AI-assisted RPA automation harness. Describe a task or provide step-by-step instructions, input files, and secret names → the system helps build, run, debug, repair, and improve automations.

## Layers

```
.agents/          ← Agent governance (rules, skills)
docs/             ← Contracts and policies
harness/          ← Deterministic Python runner
  core/           ← Session, step, result, evidence
  drivers/        ← Playwright, Windows UIA, API
  verification/   ← Success checks and contracts
  resilience/     ← Errors, retry, healing, recovery
  selectors/      ← Priority ladder and cache
  rpa/            ← Excel, workflow, retry, queue, office
  ai/             ← Agent loop, vision, planner, tools
  memory/         ← RPA Memory sessions, observations, summaries, search
  reporting/      ← HTML, JSON, failure reports
tools/            ← CLI utilities (inspect, analyze, patch)
runs/             ← Run artifacts per execution
workflows/        ← YAML workflow definitions
tests/            ← pytest test suite
config/           ← YAML config templates
```

## Execution Flow

```
User request → Codex plans → YAML workflow created
  → harness.cli validate → harness.cli run
  → deterministic step execution with verification
  → success checks per step
  → failure → failure_report.json + evidence
  → Codex reads failure → proposes patch → tests verify
  → proven lessons → RPA Memory (sessions, observations, summaries, search)
```

## Safety Boundaries

- Runtime LLM: allowed for planning, diagnosis, summarization, selector healing, report analysis
- Runtime LLM: NEVER directly executes destructive business actions without workflow approval gates
- Core harness: protected, requires mutation protocol to edit
- Credentials: never in code, logs, screenshots, memory, or reports
- Self-improvement: requires reproduced failure + root cause + passing tests
