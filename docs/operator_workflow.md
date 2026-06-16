# Operator Workflow

Use the harness as a deterministic loop:

1. Validate the workflow.
2. Run preflight.
3. Inspect or discover selectors when needed.
4. Run one phase.
5. Pause before risky steps.
6. Run one record when the workflow supports record ids.
7. Open the run report.
8. Inspect evidence and repair packets.
9. Retry only when safe retry says yes or an operator approves the risk.

Commands:

```bash
python main.py --validate-yaml workflows/upload_invoices.yaml
python main.py --preflight-yaml workflows/upload_invoices.yaml
python main.py --run-yaml workflows/upload_invoices.yaml --phase login
python main.py --run-yaml workflows/upload_invoices.yaml --pause-before submit_invoice
python main.py --runs-list
python main.py --runs-show RUN_ID
python main.py --logs-show RUN_ID --log-step submit_invoice
python main.py --report-open RUN_ID
python main.py --run-yaml workflows/upload_invoices.yaml --only-record INV-1001
python main.py --retry-run RUN_ID --failed-records
```

Run artifacts:

- `run_manifest.json`: run index, status, counts, artifact paths.
- `preflight.json`: blocking checks and warnings before execution.
- `timeline.jsonl`: phase, step, verification, evidence, and repair events.
- `records.jsonl`: append-only latest record state when YAML steps declare `record_id`.
- `report.html` and `report.json`: operator-readable run summary.
- `failure_report.json`, `evidence_bundle.json`, `repair_packet.json`: failed-step repair context.

Safe retry:

- YAML `--only-record` runs only steps whose `record_id` matches.
- `--retry-run RUN_ID --failed-records` retries only failed records whose latest `records.jsonl` entry has `safe_retry.status == "yes"`.
- Unsafe or unknown retry states stay blocked.

Secrets must stay as secret names in workflows. Reports, logs, evidence, memory, and repair packets must be redacted before writing.
