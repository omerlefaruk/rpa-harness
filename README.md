# rpa-harness

`rpa-harness` is a deterministic, evidence-backed RPA automation harness for browser, desktop, API, Excel, and YAML-driven workflows.

The core rule is simple: an action executing is not success. A workflow step only passes after explicit success checks pass. Runs should produce evidence, reports, repair guidance, and redacted artifacts that operators and AI agents can inspect.

## Typical operator flow

```bash
python main.py --validate-workflow workflows/examples/minimal_example.yaml
python main.py --preflight-workflow workflows/examples/minimal_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml
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
