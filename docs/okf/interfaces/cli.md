---
type: CLI Reference
title: rpa-harness CLI
description: Command surface for validating, preflighting, running, reporting, and maintaining automation workflows.
tags: [rpa-harness, cli, operators]
timestamp: 2026-06-17T00:00:00Z
---

# Commands

The CLI lives in `main.py`. Operators and agents use it for workflow validation, preflight, execution, reports, selector repair, copilot sessions, autopilot execution, and OKF maintenance.

# Examples

```bash
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
