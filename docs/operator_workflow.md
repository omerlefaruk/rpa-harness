# Operator Workflow

Recommended flow:

```bash
python main.py --migrate-workflow workflows/legacy.yaml --workflow-output workflows/current.yaml --migration-report migration_report.md
python main.py --validate-yaml workflows/current.yaml
python main.py --preflight-yaml workflows/current.yaml
python main.py --workflow-graph workflows/current.yaml --workflow-graph-output workflow_graph.json
python main.py --run-yaml workflows/current.yaml --phase login
python main.py --live-tail RUN_ID
python main.py --observability-index --runs-dir runs
python main.py --serve --port 8080
```

Failure investigation:

1. Open `runs/<run_id>/report.html`.
2. Inspect `timeline.jsonl` for failed phase and step.
3. Open `evidence_bundle.json`.
4. Open `repair_packet.json`.
5. Check `records.jsonl` for safe retry status.
6. Retry only records marked safe, using the CLI path, not the dashboard.

The dashboard is for observing, searching, and inspecting evidence. It does not run production retries or apply repairs.
