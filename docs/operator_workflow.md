# Operator Workflow

Recommended flow:

```bash
python main.py --migrate-workflow projects/current/workflows/legacy.yaml --workflow-output projects/current/workflows/main.yaml --migration-report migration_report.md
python main.py --validate-yaml projects/current/workflows/main.yaml
python main.py --preflight-yaml projects/current/workflows/main.yaml
python main.py --workflow-graph projects/current/workflows/main.yaml --workflow-graph-output workflow_graph.json
python main.py --run-yaml projects/current/workflows/main.yaml --phase login
python main.py --live-tail RUN_ID
python main.py --runs-list
python main.py --runs-show RUN_ID
python main.py --logs-show RUN_ID --logs-tail 50
python main.py --report-open RUN_ID
```

Failure investigation:

1. Open `runs/<run_id>/report.html`.
2. Inspect `timeline.jsonl` for failed phase and step.
3. Open `evidence_bundle.json`.
4. Open `repair_packet.json`.
5. Check `records.jsonl` for safe retry status.
6. Retry only records marked safe, using the CLI path.

Run artifacts are the operator evidence surface and source of truth. Scan `runs/` with `--runs-list`, then inspect a run with `--runs-show`, `--logs-show`, and `--report-open`; do not maintain a separate database truth system.
