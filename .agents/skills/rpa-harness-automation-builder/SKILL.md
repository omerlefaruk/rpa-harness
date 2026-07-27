---
name: rpa-harness-automation-builder
description: Canonical ActiveGraph-native automation authoring skill for rpa-harness.
---

# ActiveGraph automation authoring

This is the **only** canonical skill for authoring automations in rpa-harness.
Procedures live here. Verification, authority, redaction, retry, reconciliation,
repair admission, and tool allowlists are **executable** in
`harness.automation` — do not re-implement them in prompts.

## Lifecycle (application seam)

Use `AutomationApplication` only:

1. **Intent** — business objective, required capabilities, no unresolved ambiguity.
2. **Discovery evidence** — selectors and observations (evidence, not truth).
3. **Proposal** — model may draft; compiler/`validate_proposal` is deterministic.
4. **Validation** — fail closed on invalid class, plaintext secrets, weak unverified selectors.
5. **Registration** — immutable Definition Version + content hash.
6. **Approval** — grant bound to version, hash, scopes, actor, expiry (R3/R4).
7. **Execution** — read-only or approval-gated write; Action Attempt before I/O.
8. **Verification** — explicit post-action Verification Result + Evidence Reference.
9. **Inspection** — `inspect_run` for status, budgets, blocked_reason, next_required.
10. **Reconciliation** — unknown writes → `needs_reconciliation`; read-only only.
11. **Repair** — fork trial, promote new version or reject; never patch live parent.
12. **Promotion** — new Definition Version preserves previous.

## Non-negotiables

- EventStore is lifecycle authority; filesystem outputs are projections/exports.
- R0–R4 action classes are immutable; missing/invalid fail closed.
- Secrets: names/handles only at agent surfaces; plaintext only at local edge.
- Writes: at-most-once per run/action/idempotency scope until not_applied.
- Models cannot raise budgets, change allowlists, force success, or retry writes.
- MCP/CLI adapters call application methods only — no shell/raw driver tools.

## Thin guidance pointers

- Selectors: `.agents/skills/selector-strategies/SKILL.md` (priority ladders match executables).
- Browser recon: `.agents/skills/playwright-automation/SKILL.md` (discovery only).
- Desktop recon: `.agents/skills/windows-ui-automation/SKILL.md` (discovery only).
- Failures: `.agents/skills/error-recovery/SKILL.md` (maps to terminal states).
- Excel rows: `.agents/skills/excel-workflows/SKILL.md` (capability port, not YAML).

## AI agent loop (MCP or CLI)

You (the model) write JSON files; you never get shell or raw drivers.

1. Init workspace / status  
2. Draft proposal JSON → `validate_automation_proposal` → `register_automation_proposal`  
3. `grant_automation_approval` (R3/R4)  
4. `execute_automation_read` or `execute_automation_write` (capability `op` + port)  
5. `inspect_automation_run` / `export_automation_evidence`  
6. If `needs_reconciliation` → `reconcile_automation_run`  
7. If selector failed → propose / trial / promote repair  

```text
python -m harness.cli --automation-list-operations
python -m harness.cli --automation-validate-proposal proposal.json
python -m harness.cli --automation-register-proposal proposal.json --automation-workspace <ws>
python -m harness.cli --automation-execute-write request.json --automation-workspace <ws>
python -m harness.cli --automation-inspect <run_id> --automation-workspace <ws>
npx rpa-harness-agent mcp
```
