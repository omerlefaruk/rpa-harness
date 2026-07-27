---
type: Automation Playbook
title: MCP agent operations
description: Allowlisted MCP/CLI agent loop for ActiveGraph proposal, approval, execute, evidence, reconcile, and repair.
tags: [rpa-harness, mcp, agents, activegraph]
timestamp: 2026-07-27T00:00:00Z
---

# Agent loop

Agents draft proposal JSON and call allowlisted operations only. No shell, raw drivers, or YAML runner tools.

1. Init workspace / workspace status  
2. Validate then register Automation Proposal  
3. Grant approval for R3/R4 writes  
4. Execute read or write via capability port  
5. Inspect run / export evidence  
6. Reconcile if `needs_reconciliation`  
7. Propose / trial / promote repair on failure  

# Approved surfaces

* MCP: `packages/rpa-harness-agent` (`npx rpa-harness-agent mcp`)
* CLI: `python main.py --automation-*` or `python -m harness.cli --automation-*`
* Manifest: `.agents/config/agent_command_manifest.json`
* Skill: `.agents/skills/rpa-harness-automation-builder`

# Relationships

* Calls the [CLI](/interfaces/cli.md).
* Executes through [ActiveGraph automation](/runtime/activegraph-automation.md).
* Must follow [agent rules](/agents/agent-rules.md).

# Citations

[1] [Operator workflow](../../operator_workflow.md)
[2] [Automation builder skill](../../../.agents/skills/rpa-harness-automation-builder/SKILL.md)
[3] [Agent package README](../../../packages/rpa-harness-agent/README.md)
