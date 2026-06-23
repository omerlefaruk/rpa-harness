---
type: System
title: rpa-harness
description: Deterministic, evidence-backed automation harness for browser, desktop, API, Excel, and YAML workflows.
tags: [rpa-harness, system, automation]
timestamp: 2026-06-17T00:00:00Z
---

# Role

`rpa-harness` executes explicit automation workflows and records proof. The core rule is that an action executing is not success; workflow steps pass only after success checks pass.

YAML workflows are the only supported runtime. Operators use terminal commands and run artifacts. Run artifacts are the source of truth. No dashboard, React frontend, SQLite observability DB, class workflow runtime, local subagent framework, Office/PDF layer, or job queue is part of the core.

# Relationships

* Uses the [CLI](/interfaces/cli.md) as the operator and agent entrypoint.
* Runs deterministic YAML through the [workflow runner](/runtime/workflow-runner.md).
* Exposes governed build/run loops through [copilot and autopilot](/automation/copilot-autopilot.md).
* Is constrained by [agent rules](/agents/agent-rules.md).

# Citations

[1] [README](../../../README.md)
[2] [Architecture notes](../../architecture.md)
