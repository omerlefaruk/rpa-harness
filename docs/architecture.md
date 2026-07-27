# Architecture — ActiveGraph rpa-harness

## Overview

Local-first, **ActiveGraph-native** automation product. Operators and agents admit typed Automation Proposals, register immutable Definition Versions, execute through capability ports, and inspect EventStore projections. Action execution is not success; completion requires explicit Verification Results (and Approval Grants for R3/R4 writes).

There is **no** YAML workflow runtime, DSL compiler, copilot/autopilot session runner, dashboard, React frontend, class workflow runtime, local subagent framework, Office/PDF layer, or job queue in the core product surface.

## Layers

```text
You / AI
  → packages/rpa-harness-agent (MCP allowlist)
  → harness/cli.py  (--automation-* only)
      → harness.automation.AutomationApplication
          → ActiveGraph EventStore (data/automation-events.sqlite)
          → capability ports → ToolResult only
              → harness/drivers/*  (Playwright, Windows UIA, API adapters)
      → harness/reporting/*  (evidence export / HTML helpers)
.agents/          Agent rules + skills (playbooks; not enforcement)
docs/okf/         Indexed durable knowledge
docs/adr/         Architecture decisions
CONTEXT.md        Domain glossary
tests/            Contract and integration tests
```

## Lifecycle authority

| Concern | Authority |
| --- | --- |
| Run status, attempts, verification, blocks | EventStore append-only events |
| Definition Version immutability | Content-hash registration events |
| Approval for writes | Approval Grant events bound to version/hash/scopes |
| Filesystem JSON/HTML | Projections / exports **after** Evidence Reference events |

## Execution flow

```text
Intent + DiscoveryEvidence + Definition  (proposal JSON)
  → validate_proposal (fail closed)
  → register_proposal → Definition Version
  → grant_approval (R3/R4)
  → execute_read / execute_write via capability port
  → Verification Result + Evidence Reference
  → inspect_run / export_evidence
  → reconcile if needs_reconciliation
  → repair fork: propose → trial → promote | reject
```

## Capability ports and drivers

Drivers never write lifecycle events. They implement ports that return `ToolResult`. `AutomationApplication` records Action Attempt **before** I/O and records verification after.

Selector ladders (executable):

- Browser: `role → label → test_id → css → xpath → coordinate`
- Desktop: `automation_id → name → class → tree_path → image → coordinate`

## Safety boundaries

- Runtime models draft proposals only; admission is deterministic code
- Models cannot raise budgets, change allowlists, force success, or auto-retry writes
- Credentials: names only on agent surfaces; values only at local edge
- Skills summarize procedure; they must never be the only place a safety rule exists

## Related

- `CONTEXT.md` — glossary
- `docs/adr/ADR-0001-yaml-runtime-retired.md`
- `docs/adr/ADR-0002-skills-are-not-enforcement.md`
- `docs/adr/ADR-0003-eventstore-lifecycle-authority.md`
- `docs/research/code-vs-skill-boundary.md`
