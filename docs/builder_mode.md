# Authoring Mode (ActiveGraph)

> **Note:** Legacy “builder mode” (copilot sessions, YAML drafts under `builder_sessions/`) is retired. Authoring now means drafting **Automation Proposals** for `AutomationApplication`.

## Authoring loop

1. **Intent** — business objective, required capabilities, no unresolved ambiguity.
2. **Discovery** — browser/desktop/API observations as evidence (not executable truth).
3. **Proposal** — Intent + DiscoveryEvidence + Definition (model may draft JSON).
4. **Validation** — deterministic `validate_proposal` (fail closed on weak unverified selectors, plaintext secrets, unknown capabilities, missing success checks).
5. **Registration** — immutable Definition Version + content hash.
6. **Approval** — grant for R3/R4 writes bound to version, hash, scopes, actor, expiry.
7. **Execution** — capability port; Action Attempt before I/O; Verification Result after.
8. **Repair** — fork trial only; promote new version or reject.

Canonical skill: `.agents/skills/rpa-harness-automation-builder`.

## Commands

```bash
python main.py --automation-list-operations
python main.py --automation-validate-proposal proposal.json
python main.py --automation-register-proposal proposal.json --automation-workspace <ws>
python main.py --automation-propose-repair request.json --automation-workspace <ws>
python main.py --automation-trial-repair request.json --automation-workspace <ws>
python main.py --automation-promote-repair request.json --automation-workspace <ws>
npx rpa-harness-agent mcp
```

## Required behavior

- Every executable action needs explicit verification / success checks.
- Risky writes need Approval Grants.
- External writes are at-most-once per run/action/idempotency scope until not applied.
- Weak selectors require verified=true (and policy/approval as coded).
- Discovery failures should block admission — do not invent coordinates.
