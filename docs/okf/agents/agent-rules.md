---
type: Agent Policy
title: Agent rules
description: Local rules that keep automation explicit, validated, redacted, and evidence-backed.
tags: [rpa-harness, agents, policy]
timestamp: 2026-06-17T00:00:00Z
---

# Rules

Agents may inspect, draft, repair, and explain workflows. Production execution must remain explicit, validated, and evidence-backed. Secret values must not be hardcoded, logged, reported, stored, serialized, or added to OKF.

YAML workflows are the only supported runtime. Operators use terminal commands and run artifacts. Run artifacts are the source of truth. No dashboard, React frontend, SQLite observability DB, class workflow runtime, local subagent framework, Office/PDF layer, or job queue is part of the core.

# OKF Maintenance

When agents change docs, workflow schema, CLI commands, skills, or automation policy, they should update the relevant OKF concept, regenerate indexes, and validate the bundle.

# Issue Planning

GitHub Issues is the canonical specification and implementation-ticket tracker. Agent-ready work is identified by the `ready-for-agent` label and must have no open blockers or assignee. The repository's issue-tracker, triage-label, and domain-documentation conventions are defined under `docs/agents`.

# Relationships

* Governs the [rpa-harness system](/system/rpa-harness.md).
* Applies to the [CLI](/interfaces/cli.md) and [copilot/autopilot loops](/automation/copilot-autopilot.md).

# Citations

[1] [AGENTS rules](../../../AGENTS.md)
[2] [Issue tracker conventions](../../agents/issue-tracker.md)
[3] [Triage label conventions](../../agents/triage-labels.md)
[4] [Domain documentation conventions](../../agents/domain.md)
