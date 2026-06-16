---
type: Agent Policy
title: Agent rules
description: Local rules that keep automation explicit, validated, redacted, and evidence-backed.
tags: [rpa-harness, agents, policy]
timestamp: 2026-06-17T00:00:00Z
---

# Rules

Agents may inspect, draft, repair, and explain workflows. Production execution must remain explicit, validated, and evidence-backed. Secret values must not be hardcoded, logged, reported, stored, serialized, or added to OKF.

# OKF Maintenance

When agents change docs, workflow schema, CLI commands, skills, or automation policy, they should update the relevant OKF concept, regenerate indexes, and validate the bundle.

# Relationships

* Governs the [rpa-harness system](/system/rpa-harness.md).
* Applies to the [CLI](/interfaces/cli.md) and [copilot/autopilot loops](/automation/copilot-autopilot.md).

# Citations

[1] [AGENTS rules](../../../AGENTS.md)
