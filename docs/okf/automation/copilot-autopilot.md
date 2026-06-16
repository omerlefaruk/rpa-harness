---
type: Automation Playbook
title: Copilot and autopilot loops
description: Governed agent-facing loops for building, validating, preflighting, and running deterministic automations.
tags: [rpa-harness, copilot, autopilot, agents]
timestamp: 2026-06-17T00:00:00Z
---

# Modes

Copilot mode asks questions at intake, uncertainty, risk, or review gates. Autopilot mode is for already-authored deterministic workflow execution and is constrained by `.agents/config/autopilot.yaml`.

# Approved Commands

Agents should prefer the command manifest over free-form shell invention:

```bash
python main.py --copilot-auto task.md --builder-session-id SESSION
python main.py --copilot-try-url https://example.test --copilot-try-workflow workflow.yaml --builder-session-id SESSION
python main.py --autopilot-build task.md --autopilot-workflow workflow.yaml
```

# Relationships

* Calls the [CLI](/interfaces/cli.md).
* Executes through the [workflow runner](/runtime/workflow-runner.md).
* Must follow [agent rules](/agents/agent-rules.md).

# Citations

[1] [Operator workflow](../../operator_workflow.md)
[2] [Automation builder skill](../../../skills/rpa_harness_automation_builder/SKILL.md)
