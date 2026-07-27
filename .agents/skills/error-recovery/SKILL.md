---
name: error-recovery
description: Maps operator recovery to ActiveGraph terminal states and repair/reconcile.
---

# Failure and recovery

Executable terminal states: `completed`, `failed`, `blocked`,
`needs_reconciliation`, `rejected`, `cancelled`.

| Symptom | State | Next |
| --- | --- | --- |
| Verification failed | `failed` | Inspect evidence; repair trial if selector |
| Budget/spiral | `blocked` | Human or external state change (`next_required`) |
| Unknown write | `needs_reconciliation` | Read-only reconcile only |
| Still unknown | terminal unattended | Human inspection |
| Weak/unverified selector | rejected at proposal | Strengthen selector |
| Stale parent on promote | repair rejected | Re-base repair on latest version |

Do not invent retries for non-idempotent writes. Canonical lifecycle:
`rpa-harness-automation-builder`.
