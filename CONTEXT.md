# CONTEXT — rpa-harness domain glossary

Single-context domain vocabulary for this repository. Use these terms exactly in issues, specs, code, tests, and agent prose. Architecture decisions live under `docs/adr/`.

## Product

| Term | Meaning |
| --- | --- |
| **rpa-harness** | Deterministic ActiveGraph-native automation product with evidence. Not a free-form agent with shell. |
| **ActiveGraph** | Event-sourced substrate; EventStore is lifecycle authority. |
| **AutomationApplication** | Application seam (`harness.automation.AutomationApplication`) that admits proposals, records events, executes via capability ports, and projects runs. Sole writer of lifecycle events for a workspace lock holder. |

## Authoring & definitions

| Term | Meaning |
| --- | --- |
| **Automation Intent** | Business objective, required capabilities, and constraints. No unresolved business ambiguity at admission. |
| **Discovery Evidence** | Observed selectors/capabilities from recon. Evidence only — not executable truth. |
| **Automation Proposal** | Intent + Discovery Evidence + Definition drafted by an agent/model; subject to deterministic validation. |
| **Automation Definition** | Typed definition of actions, classes, success checks, scopes, and secret **names**. |
| **Definition Version** | Immutable registered definition with content hash. Live parents are never patched in place. |

## Execution & risk

| Term | Meaning |
| --- | --- |
| **Action class R0–R4** | Immutable risk classes. R0 is read-oriented; higher classes gate writes and require stronger policy/approval. Missing/invalid class fails closed. |
| **Approval Grant** | Time- and scope-bound grant tied to a Definition Version hash, actor, and scopes; required for R3/R4 writes. |
| **Capability Port** | Application-facing port (browser/API/excel/desktop) that returns **ToolResult** only and never writes lifecycle events. |
| **ToolResult** | Value/error payload from a capability port after I/O. |
| **Verification Result** | Explicit post-action proof recorded as an event. Action execution ≠ success. |
| **Evidence Reference** | Event pointing at an evidence artifact; filesystem export follows the reference. |

## Lifecycle operations

| Term | Meaning |
| --- | --- |
| **EventStore** | Append-only ActiveGraph store (typically `data/automation-events.sqlite` per workspace). Sole lifecycle authority. |
| **Run / Run summary** | Projection rebuilt by replaying events; inspect never invents state outside the log. |
| **Workspace runtime pin** | Immutable product release pin for a workspace (status / upgrade / rollback). |
| **Reconcile** | Operator-assisted resolution when a write is ambiguous (`needs_reconciliation`); further work is read-only until resolved. |
| **Repair fork** | propose → trial on a fork → promote new Definition Version or reject. Never mutates the live parent version. |

## Terminal run states (executable)

`completed`, `failed`, `blocked`, `needs_reconciliation`, `rejected`, `cancelled`.

## Selectors (executable priority)

- **Browser:** `role → label → test_id → css → xpath → coordinate`
- **Desktop:** `automation_id → name → class → tree_path → image → coordinate`

Weak strategies require verification (and approval when coded policy demands).

## Agent surfaces

| Term | Meaning |
| --- | --- |
| **MCP agent loop** | Allowlisted tools in `packages/rpa-harness-agent` mapping to application methods. |
| **Canonical skill** | `.agents/skills/rpa-harness-automation-builder` — procedure only. |

## Retired terms (do not use as product paths)

YAML runner, `--run-yaml`, DSL, copilot session, autopilot build, `builder_sessions` as primary authoring, projects/workflows trees as runtime roots.

## Related

- `docs/adr/ADR-0001-yaml-runtime-retired.md`
- `docs/adr/ADR-0002-skills-are-not-enforcement.md`
- `docs/adr/ADR-0003-eventstore-lifecycle-authority.md`
- `docs/research/code-vs-skill-boundary.md`
- `docs/agents/domain.md`
