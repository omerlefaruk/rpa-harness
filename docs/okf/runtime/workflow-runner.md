---
type: Runtime
title: YAML workflow runner
description: Runtime that validates, preflights, executes, verifies, and reports deterministic YAML workflow steps.
tags: [rpa-harness, runtime, workflow]
timestamp: 2026-06-17T00:00:00Z
---

# Behavior

The YAML runner loads workflow definitions, resolves declared inputs and secrets at the execution edge, runs preflight checks, executes steps, evaluates success checks, and writes redacted run artifacts.

# Evidence

Runs may write `timeline.jsonl`, `run_manifest.json`, `preflight.json`, `records.jsonl`, `evidence_bundle.json`, `repair_packet.json`, `report.json`, and `report.html`.

# Relationships

* Invoked from the [CLI](/interfaces/cli.md).
* Governed by [agent rules](/agents/agent-rules.md).
* Used by [copilot and autopilot](/automation/copilot-autopilot.md).

# Citations

[1] [Workflow spec](../../workflow_spec.md)
[2] [Verification contract](../../verification_contract.md)
