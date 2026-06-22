---
type: CLI Reference
title: rpa-harness CLI
description: Command surface for validating, preflighting, running, reporting, and maintaining automation workflows.
tags: [rpa-harness, cli, operators]
timestamp: 2026-06-17T00:00:00Z
---

# Commands

The packaged CLI lives in `harness.cli` and remains available through the compatibility shim `main.py`. Operators and agents use it for workflow validation, preflight, execution, reports, selector repair, copilot sessions, autopilot execution, and OKF maintenance.


# Product launcher

`roi-harness` is a thin npm launcher for consumer workspaces. It creates `.rpa-harness/venv`, installs the Python runtime, initializes workspace folders, and exposes a governed MCP stdio bridge backed by `.agents/config/agent_command_manifest.json`-style allowlisted commands.

# Examples

```bash
npx roi-harness init
npx roi-harness validate workflows/example.yaml
npx roi-harness mcp
python main.py --validate-yaml projects/example_data_verification/workflows/main.yaml
python main.py --preflight-yaml projects/example_data_verification/workflows/main.yaml
python main.py --run-yaml projects/example_data_verification/workflows/main.yaml
python scripts/okf.py validate docs/okf
```

# Relationships

* Entry point for the [workflow runner](/runtime/workflow-runner.md).
* Approved agent commands are listed in `.agents/config/agent_command_manifest.json`.

# Citations

[1] [README](../../../README.md)
[2] [Main CLI](../../../main.py)
