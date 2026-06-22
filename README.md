# rpa-harness

`rpa-harness` is a deterministic, evidence-backed RPA automation harness for browser, desktop, API, Excel, and YAML-driven workflows.

The core rule is simple: an action executing is not success. A workflow step only passes after explicit success checks pass. Runs should produce evidence, reports, repair guidance, and redacted artifacts that operators and AI agents can inspect.


## Install as an AI-agent workspace product

```bash
npx roi-harness init
npx roi-harness validate workflows/example.yaml
npx roi-harness mcp
```

The npm package is a thin launcher. The real runtime stays in Python inside `.rpa-harness/venv`, and the generated workspace contains `workflows/`, `config/`, `.agents/`, `runs/`, and `reports/`. AI agents should connect through `npx roi-harness mcp`; it exposes allowlisted workflow tools only, not arbitrary shell access.

## Typical operator flow

```bash
python main.py --validate-yaml workflows/examples/default_schema_example.yaml
python main.py --preflight-yaml workflows/examples/default_schema_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml
python main.py --audit-workflow projects/operaRezervasyon/workflows/main.yaml
python main.py --config projects/example_data_verification/config.yaml --run-workflows --discover-wf projects/example_data_verification
python main.py --observability-index --runs-dir runs
python main.py --runs-list
python main.py --runs-show <RUN_ID>
python main.py --report-open <RUN_ID>
```

## OKF knowledge bundle

Repo knowledge is published as an OKF v0.1 bundle under `docs/okf`:

```bash
python scripts/okf.py validate docs/okf
python scripts/okf.py generate-indexes docs/okf
git config core.hooksPath .githooks
```

The pre-commit hook validates the OKF bundle and runs `tests/test_okf_bundle.py`.

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
- Secret values must never be hardcoded, logged, reported, or included in repair packets.
- Browser selectors should prefer stable selectors such as `data-testid`, role/name, label, placeholder, text, id, CSS, then XPath.
- Desktop selectors should prefer automation IDs, name/control type, class/control type, tree paths, image anchors, then coordinates as last resort.
## Tiny DSL compile flow

Use `.rpa` files as a small, readable authoring layer. They compile to the existing schema v2 YAML format; YAML validation, preflight, execution, evidence, and reports still use the normal harness paths.

```bash
python main.py --validate-dsl workflows/examples/download_invoice.rpa
python main.py --compile-dsl workflows/examples/download_invoice.rpa --workflow-output .pytest_tmp/download_invoice.yaml
python main.py --validate-yaml .pytest_tmp/download_invoice.yaml
```
## Default schema and artifacts

Real projects must live under `projects/<project>/`:

```text
projects/<project>/
  workflows/main.yaml
  config.yaml
  tests/test_workflow.py
  README.md
```

Shared harness examples remain under `workflows/examples/` and `workflows/capabilities/`.
New project workflows should use the phase-based default schema. Legacy flat examples can be migrated:

```bash
python main.py --migrate-workflow workflows/examples/minimal_example.yaml --workflow-output workflows/examples/minimal_example.schema.yaml --migration-report migration_report.md
python main.py --workflow-graph workflows/examples/default_schema_example.yaml --workflow-graph-output workflow_graph.json
```

Run artifacts under `runs/` are the source of truth for operator inspection.
