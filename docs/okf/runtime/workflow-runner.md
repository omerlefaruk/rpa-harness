---
type: Runtime
title: YAML workflow runner
description: Runtime that validates, preflights, executes, verifies, and reports deterministic YAML workflow steps.
tags: [rpa-harness, runtime, workflow]
timestamp: 2026-06-17T00:00:00Z
---

# Behavior

The YAML runner is the only workflow runtime. It loads workflow definitions, resolves declared inputs and secrets at the execution edge, runs preflight checks, executes steps, evaluates success checks, and writes redacted run artifacts.

YAML workflows are the only supported runtime. Operators use terminal commands and run artifacts. Run artifacts are the source of truth. No dashboard, React frontend, SQLite observability DB, class workflow runtime, local subagent framework, Office/PDF layer, or job queue is part of the core.

# Evidence

Runs may write `timeline.jsonl`, `run_manifest.json`, `preflight.json`, `records.jsonl`, `evidence_bundle.json`, `repair_packet.json`, `report.json`, and `report.html`.

Shared artifact path and JSON/JSONL reads live in `harness.core.artifacts`; run artifact scanning and reporting commands consume those helpers instead of owning parallel readers.

Operators inspect run folders directly with `--runs-list`, `--runs-show`, `--logs-show`, and `--report-open`.

# Relationships

* Invoked from the [CLI](/interfaces/cli.md).
* Governed by [agent rules](/agents/agent-rules.md).
* Used by [copilot and autopilot](/automation/copilot-autopilot.md).

# Citations

[1] [Workflow spec](../../workflow_spec.md)
[2] [Verification contract](../../verification_contract.md)
