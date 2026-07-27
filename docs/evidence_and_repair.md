# Evidence and Repair

> **ActiveGraph lifecycle SoT:** the EventStore is lifecycle authority. Use `inspect` / `export_evidence` first. Filesystem bundles and HTML reports are projections/exports, not a second source of truth.

Repair starts with evidence, not guesses. Prefer propose → trial (fork) → promote repair ops over patching live Definition Versions.

## Inspect these surfaces

- EventStore projections via `--automation-inspect` / MCP `inspect_automation_run`
- Evidence exports via `--automation-export-evidence`
- `evidence_bundle.json` / selector evidence / screenshots when exported
- `repair` proposal/trial records in the EventStore
- `report.html` when an operator export is present
- DOM / UIA / API artifacts where available

### Historical YAML-era filenames (archive / export only)

- `run_manifest.json`, `timeline.jsonl`, `preflight.json`, `records.jsonl`, `repair_packet.json`

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
