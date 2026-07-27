---
type: Runtime
title: ActiveGraph automation
description: Event-sourced automation lifecycle — proposal, approval, execute, verify, reconcile, repair, and evidence export.
tags: [rpa-harness, activegraph, runtime, evidence]
timestamp: 2026-07-27T00:00:00Z
---

# Behavior

`harness.automation.AutomationApplication` is the shared application interface for the ActiveGraph-native product. It accepts versioned typed Automation Intents, Discovery Evidence, Automation Proposals, Definitions, and immutable Definition Versions. Model output is only an Automation Proposal; deterministic validation decides whether it can be registered.

## Lifecycle

1. **Propose / validate** — admit Intent + DiscoveryEvidence + Definition; fail closed on unknown capabilities, plaintext secrets, missing success checks, unresolved business ambiguity, and weak unverified selectors.
2. **Register** — immutable Definition Version + content hash events.
3. **Grant approval** — bound to version, hash, scopes, actor, and expiry for R3/R4 writes.
4. **Execute read / write** — capability port returns `ToolResult` only; Action Attempt is recorded before I/O.
5. **Verify** — explicit Verification Result; Run becomes `completed` only on pass, else `failed` with `failure_kind`.
6. **Inspect / export evidence** — projections from EventStore; Evidence Reference event precedes filesystem export.
7. **Reconcile** — ambiguous writes enter `needs_reconciliation`; further work is read-only until resolved.
8. **Repair** — propose → trial on a fork → promote new Definition Version or reject; never patch the live parent.

Secret references use names only. Budgets for proposals and model calls are bounded at the application boundary. Action classes R0–R4 are immutable and fail closed when missing/invalid.

## Workspace

Each workspace uses `data/automation-events.sqlite` (or the application-configured EventStore path). Only one write-capable application instance holds the workspace lock. Read-only inspectors rebuild summaries from the event log. Workspace runtime pins support status / upgrade / rollback via CLI.

# Evidence

The application appends an Evidence Reference before writing referenced JSON evidence export. Terminal states include `completed`, `failed`, `blocked`, `needs_reconciliation`, `rejected`, and `cancelled`.

# Interfaces

CLI flags (also via `python -m harness.cli`):

* `--automation-init-workspace`, `--automation-workspace-status`, `--automation-workspace-upgrade`, `--automation-workspace-rollback`
* `--automation-list-operations`, `--automation-validate-proposal`, `--automation-register-proposal`, `--automation-propose`
* `--automation-grant-approval`, `--automation-execute-read`, `--automation-execute-write`
* `--automation-inspect`, `--automation-export-evidence`, `--automation-reconcile`
* `--automation-propose-repair`, `--automation-trial-repair`, `--automation-promote-repair`, `--automation-reject-repair`

MCP exposes the same allowlisted operations; never shell or raw drivers.

# Relationships

* Invoked from the [CLI](/interfaces/cli.md).
* Driven by agents via [MCP agent operations](/automation/agent-mcp.md).
* Supersedes the retired [YAML workflow runner](/runtime/workflow-runner.md) historical note.

# Citations

[1] [Architecture](../../architecture.md)
[2] [Operator workflow](../../operator_workflow.md)
[3] [Automation builder skill](../../../.agents/skills/rpa-harness-automation-builder/SKILL.md)
