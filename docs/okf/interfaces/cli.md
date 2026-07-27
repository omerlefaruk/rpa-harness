---
type: CLI Reference
title: rpa-harness CLI
description: ActiveGraph-only command surface for workspace, proposal, approval, execute, inspect, reconcile, and repair operations.
tags: [rpa-harness, cli, operators, activegraph]
timestamp: 2026-07-27T00:00:00Z
---

# Commands

The packaged CLI lives in `harness.cli` and remains available through the compatibility shim `main.py`. Operators and agents use **only** `--automation-*` flags. YAML, DSL, copilot, and autopilot flags are not part of the CLI surface.

ActiveGraph uses the workspace SQLite EventStore as lifecycle authority. Filesystem evidence is an export written after its Evidence Reference event is accepted.

# Product launcher

`npx rpa-harness-agent` / `npx roi-harness` is a thin npm launcher for consumer workspaces and the MCP stdio bridge. Approved agent commands also appear in `.agents/config/agent_command_manifest.json`.

# Examples

```bash
npx rpa-harness-agent init my-workspace
npx rpa-harness-agent mcp
python main.py --automation-list-operations
python main.py --automation-init-workspace .rpa-automation
python main.py --automation-workspace-status --automation-workspace .rpa-automation
python main.py --automation-validate-proposal proposals/example_read.json
python main.py --automation-register-proposal proposals/example_read.json --automation-workspace .rpa-automation
python main.py --automation-grant-approval grant.json --automation-workspace .rpa-automation
python main.py --automation-execute-read request.json --automation-workspace .rpa-automation
python main.py --automation-execute-write request.json --automation-workspace .rpa-automation
python main.py --automation-inspect RUN_ID --automation-workspace .rpa-automation
python main.py --automation-export-evidence RUN_ID --automation-workspace .rpa-automation
python main.py --automation-reconcile request.json --automation-workspace .rpa-automation
python main.py --automation-propose-repair request.json --automation-workspace .rpa-automation
python main.py --automation-trial-repair request.json --automation-workspace .rpa-automation
python main.py --automation-promote-repair request.json --automation-workspace .rpa-automation
python scripts/okf.py validate docs/okf
```

# Relationships

* Entry point for [ActiveGraph automation](/runtime/activegraph-automation.md).
* Agent allowlist documented in [MCP agent operations](/automation/agent-mcp.md).
* Approved agent commands are listed in `.agents/config/agent_command_manifest.json`.

# Citations

[1] [README](../../../README.md)
[2] [Main CLI](../../../main.py)
