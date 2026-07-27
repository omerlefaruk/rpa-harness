---
type: Agent Policy
title: Agent rules
description: Local rules that keep ActiveGraph automation explicit, validated, redacted, and evidence-backed.
tags: [rpa-harness, agents, policy, activegraph]
timestamp: 2026-07-27T00:00:00Z
---

# Rules

Agents may inspect, draft, repair, and explain automations. Production execution must remain explicit, validated, and evidence-backed through `AutomationApplication`. Secret values must not be hardcoded, logged, reported, stored, serialized, or added to OKF.

EventStore is lifecycle authority. Skills are playbooks; code enforces safety. Selector ladders must match `harness.automation.capabilities`. Protected areas include automation lifecycle, security/credentials, AGENTS rules, and `.agents/skills`.

# OKF Maintenance

When agents change docs, CLI commands, skills, or automation policy, they should update the relevant OKF concept, regenerate indexes, and validate the bundle under `docs/okf`.

```bash
python scripts/okf.py generate-indexes docs/okf
python scripts/okf.py validate docs/okf
```

# Issue Planning

GitHub Issues is the canonical specification and implementation-ticket tracker. Agent-ready work is identified by the `ready-for-agent` label and must have no open blockers or assignee. Conventions live under `docs/agents`. Domain glossary: `CONTEXT.md`. Decisions: `docs/adr/`.

# Relationships

* Governs the [rpa-harness system](/system/rpa-harness.md).
* Applies to the [CLI](/interfaces/cli.md) and [MCP agent operations](/automation/agent-mcp.md).

# Citations

[1] [AGENTS rules](../../../AGENTS.md)
[2] [Issue tracker conventions](../../agents/issue-tracker.md)
[3] [Triage label conventions](../../agents/triage-labels.md)
[4] [Domain documentation conventions](../../agents/domain.md)
