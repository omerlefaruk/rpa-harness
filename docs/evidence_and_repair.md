# Evidence And Repair

Failures should include:

- `failure_kind`
- `evidence_bundle.json`
- screenshot, DOM, UIA, API, or log artifacts when available
- `repair_packet.json`
- timeline events linking the failure and evidence
- safe retry status
- recommended next action

Common failure kinds:

- `workflow_validation_error`
- `missing_secret`
- `selector_not_found`
- `ambiguous_selector`
- `action_failed`
- `verification_failed`
- `timeout`
- `input_data_error`
- `target_unavailable`
- `auth_failed`
- `permission_denied`
- `business_rule_rejected`
- `unexpected_state`
- `repair_candidate`

Diagnostic table:

| Symptom | Likely source |
|---|---|
| Missing success check accepted | Validator bug |
| Secret appears in report/log/memory | Redaction or secret-boundary bug |
| Action ran but no check executed | Runner bug |
| Check failed correctly with evidence | Workflow, target, or data issue |
| Failure has no evidence bundle | Reporting/evidence bug |
| Failure has no failure kind | Error classification bug |
| Selector failed but no candidates captured | Selector evidence gap |
| Retry duplicated an external record | Retry/idempotency bug |
| Report and timeline disagree | State aggregation bug |

Repair from evidence. Do not patch core harness, memory, credentials, rules, or skills without a reproduced failure, a focused test, and a minimal diff.

Selector repair is gated:

- no validated candidate: blocked
- validated candidate without approval: ready, no mutation
- validated candidate with `--repair-approve`: workflow selector patch may be applied

Every decision is written to `selector_repair_decision.json`.
