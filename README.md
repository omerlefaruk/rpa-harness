# rpa-harness

`rpa-harness` is a deterministic, evidence-backed RPA automation harness for browser, desktop, API, Excel, and YAML-driven workflows.

The core rule is simple: an action executing is not success. A workflow step only passes after explicit success checks pass. Runs should produce evidence, reports, repair guidance, and redacted artifacts that operators and AI agents can inspect.

## Typical operator flow

```bash
python main.py --validate-yaml workflows/examples/default_schema_example.yaml
python main.py --preflight-yaml workflows/examples/default_schema_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml
python main.py --observability-index --runs-dir runs
python main.py --serve --port 8080
python main.py --runs-list
python main.py --runs-show <RUN_ID>
python main.py --report-open <RUN_ID>
```

## Generated run artifacts

A run directory may contain:

- `run_manifest.json` — run index and summary.
- `timeline.jsonl` — structured phase/step/action/verification events.
- `preflight.json` — validation and environment readiness checks.
- `records.jsonl` — record-level status for data workflows.
- `evidence_bundle.json` — failure evidence manifest.
- `repair_packet.json` — compact repair context.
- `report.html` / `report.json` — operator report.

## Safety rules

- Every workflow step must include success checks unless it is an explicitly allowed no-op.
- Secret values must never be hardcoded, logged, reported, stored in memory, or included in repair packets.
- Browser selectors should prefer stable selectors such as `data-testid`, role/name, label, placeholder, text, id, CSS, then XPath.
- Desktop selectors should prefer automation IDs, name/control type, class/control type, tree paths, image anchors, then coordinates as last resort.
- Memory should store evidence, not guesses.

## Default schema and dashboard

New workflows should use the phase-based default schema. Legacy flat workflows can be migrated:

```bash
python main.py --migrate-workflow workflows/examples/minimal_example.yaml --workflow-output workflows/examples/minimal_example.schema.yaml --migration-report migration_report.md
python main.py --workflow-graph workflows/examples/default_schema_example.yaml --workflow-graph-output workflow_graph.json
```

The local dashboard API indexes run folders into `runs/observability.db` without replacing artifacts as the source of truth.
