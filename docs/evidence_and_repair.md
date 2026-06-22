# Evidence and Repair

Repair starts with evidence, not guesses.

## Inspect these files

- `run_manifest.json`
- `timeline.jsonl`
- `preflight.json`
- `records.jsonl`
- `evidence_bundle.json`
- `selector_evidence.json`
- `repair_packet.json`
- `report.html`
- screenshots, DOM snapshots, UIA snapshots, API previews, logs

## Harness bug vs workflow bug

| Symptom | Likely source |
|---|---|
| Missing success check accepted | Validator bug |
| Secret appears in report/log | Redaction or secret boundary bug |
| Action ran but no check executed | Runner bug |
| Check failed correctly with evidence | Workflow, target, or data issue |
| Failure has no evidence bundle | Reporting/evidence bug |
| Failure has no failure kind | Error classification bug |
| Selector failed but no candidates captured | Selector evidence bug |
| Retry duplicated external record | Retry/idempotency bug |
| Run cannot resume failed record | Ledger/resume bug |
| Report says failed but timeline says passed | State aggregation bug |

## Safe retry

Only retry when the report says it is safe or an operator explicitly accepts the risk. External writes, destructive actions, uploads, sends, submits, and deletes are not retryable by default.
