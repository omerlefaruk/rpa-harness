# rpa-harness Agent Rules

## Core principle

`rpa-harness` is a **deterministic, evidence-backed ActiveGraph product**. AI may inspect, draft, repair, and explain automations, but production execution stays explicit, validated, and evidence-backed. Do not introduce uncontrolled autonomy or a parallel runtime.

Primary runtime: `harness.automation.AutomationApplication` + EventStore (`data/automation-events.sqlite` per workspace). CLI is ActiveGraph-only (`--automation-*` flags). Canonical authoring skill: `.agents/skills/rpa-harness-automation-builder`. Agent MCP package: `packages/rpa-harness-agent/`.

## Before changing code

- Inspect existing modules first; reuse or refactor instead of parallel systems.
- Keep changes small and tested.
- Prefer JSON/JSONL/static HTML/local files unless the repo already uses another store for that purpose.

## OKF knowledge bundle

- `docs/okf` is the local Open Knowledge Format bundle for this repo.
- When changing docs, CLI commands, skills, project layout, hooks, or agent policy, update the related OKF concept if durable repo knowledge changes.
- Run `python scripts/okf.py generate-indexes docs/okf` after OKF concept edits.
- Run `python scripts/okf.py validate docs/okf` before finishing OKF-related work.

## Safety

- Every executable action must have explicit success / verification checks unless it is an explicitly allowed no-op.
- Action execution is not success.
- Do not hardcode, log, report, store, or serialize secret values.
- Use secret names in proposals and definitions; resolve secret values only at the execution edge.
- Redact before writing reports, logs, evidence exports, repair packets, or prompts.
- Non-idempotent external writes must not be retried automatically.

## Protected areas

Modify only with explicit justification and tests:

- `harness/automation/` lifecycle (AutomationApplication, EventStore binding, capability admission)
- security / credential policy (`harness/security.py`, `docs/credential_policy.md`)
- `AGENTS.md` and `.agents/rules/`
- `.agents/skills/`

## Selector policy (matches `harness.automation.capabilities`)

Browser priority:

`role → label → test_id → css → xpath → coordinate`

Desktop priority:

`automation_id → name → class → tree_path → image → coordinate`

Coordinate (and other weak strategies) are last resort only. They must be marked verified where required and followed by explicit verification.

## Evidence expectations

EventStore is lifecycle authority. Filesystem outputs are projections/exports.

Failures should produce or link:

- `failure_kind`
- EventStore events (inspect via automation inspect / export)
- evidence export / `evidence_bundle` artifacts where available
- screenshot / DOM / UIA / API artifacts where available
- selector evidence where selector repair is relevant
- repair proposal / trial / promote path (or reject)
- operator-facing report HTML when exported

Repair from evidence, not assumptions.

## Pointers

- Domain glossary: `CONTEXT.md`
- Architecture decisions: `docs/adr/`
- Issue tracker: `docs/agents/issue-tracker.md`
- Triage labels: `docs/agents/triage-labels.md`
- Domain docs convention: `docs/agents/domain.md`
- Verification contract: `docs/verification_contract.md`
- Credential policy: `docs/credential_policy.md`
- Code vs skill boundary: `docs/research/code-vs-skill-boundary.md`
