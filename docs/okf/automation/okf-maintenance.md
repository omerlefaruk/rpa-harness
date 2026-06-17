---
type: Automation Playbook
title: OKF maintenance
description: Validation, index generation, hook, CI, and agent command coverage for the local OKF bundle.
tags: [rpa-harness, okf, hooks, agents]
timestamp: 2026-06-17T00:00:00Z
---

# Loop

Agents and operators update `docs/okf` when durable repo knowledge changes, regenerate indexes, then validate the bundle.

# Commands

```bash
python scripts/okf.py generate-indexes docs/okf
python scripts/okf.py validate docs/okf
```

# Automation

* `.githooks/pre-commit` validates OKF and runs `tests/test_okf_bundle.py`.
* `.github/workflows/ci.yml` validates OKF on push and pull request.
* `.agents/config/agent_command_manifest.json` exposes `okf_validate` and `okf_generate_indexes`.

# Relationships

* Maintains [agent rules](/agents/agent-rules.md).
* Uses the [CLI concept](/interfaces/cli.md) as the agent command reference.

# Citations

[1] [OKF validator](../../../scripts/okf.py)
[2] [Pre-commit hook](../../../.githooks/pre-commit)
