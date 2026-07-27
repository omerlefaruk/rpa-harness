# rpa-harness Agent Rules

## Core principle

`rpa-harness` is deterministic RPA automation with evidence. Do not introduce uncontrolled autonomy. AI may inspect, draft, repair, and explain workflows, but production execution must remain explicit, validated, and evidence-backed.

## Before changing code

- Inspect existing modules first.
- Reuse or refactor existing code instead of creating parallel reporting, selector, workflow, or CLI systems.
- Keep changes small and tested.
- Prefer JSON/JSONL/static HTML/local files over servers, databases, or visual platforms unless the repo already uses them for the exact purpose.

## Safety

- Every executable workflow step must have explicit success checks unless it is an explicitly allowed no-op.
- Action execution is not success.
- Do not hardcode, log, report, store, or serialize secret values.
- Use secret names in workflow definitions; resolve secret values only at the execution edge.
- Redact before writing reports, logs, evidence bundles, repair packets, builder artifacts, or prompts.
- Non-idempotent external writes must not be retried automatically.

## Protected areas

Treat these as protected and modify only with explicit justification and tests:

- core harness/orchestrator
- credential policy
- AGENTS rules
- skills

## Selector policy

Browser priority:

`data-testid → role/name → label → placeholder → text → stable id → CSS → XPath`

Desktop priority:

`automation_id → name/control_type → class/control_type → tree path → image anchor → coordinate fallback`

Coordinate fallback is last resort only. It must be relative/calibrated where possible, marked weak, and followed by explicit verification.

## Evidence expectations

Failures should produce or link:

- `failure_kind`
- `timeline.jsonl` event
- `evidence_bundle.json`
- screenshot / DOM / UIA / API artifacts where available
- `selector_evidence.json` where selector repair is relevant
- `repair_packet.json` or `repair_packet.md`
- `report.html`

Repair from evidence, not assumptions.
