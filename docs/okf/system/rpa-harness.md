---
type: System
title: rpa-harness
description: Deterministic ActiveGraph-native automation product with EventStore lifecycle authority and evidence exports.
tags: [rpa-harness, system, automation, activegraph]
timestamp: 2026-07-27T00:00:00Z
---

# Role

`rpa-harness` executes explicit automations through `harness.automation.AutomationApplication` and records proof in an ActiveGraph EventStore. The core rule is that an action executing is not success; runs complete only after Verification Results (and Approval Grants for R3/R4 writes).

The product surface is ActiveGraph-native: CLI `--automation-*` flags, MCP allowlist in `packages/rpa-harness-agent`, capability ports returning `ToolResult`, and drivers as adapters. YAML runner, DSL, copilot, and autopilot entrypoints are retired.

Operators use terminal/MCP commands and EventStore projections. Filesystem evidence is an export after an Evidence Reference event. No dashboard, React frontend, class workflow runtime, local subagent framework, Office/PDF layer, or job queue is part of the core.

Python dependencies are declared in `pyproject.toml` and locked with `uv.lock`.

# Relationships

* Uses the [CLI](/interfaces/cli.md) as the operator and agent entrypoint.
* Runs automations through [ActiveGraph automation](/runtime/activegraph-automation.md).
* Exposes the agent loop through [MCP agent operations](/automation/agent-mcp.md).
* Is constrained by [agent rules](/agents/agent-rules.md).

# Citations

[1] [README](../../../README.md)
[2] [Architecture notes](../../architecture.md)
[3] [CONTEXT glossary](../../../CONTEXT.md)
