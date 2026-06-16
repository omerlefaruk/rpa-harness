# Operator Workflow

Use `rpa-harness` as a transparent automation cockpit:

`validate → preflight → inspect → run phase → review report → repair → retry/resume safely`

## Common commands

```bash
python main.py --validate-yaml workflows/examples/minimal_example.yaml
python main.py --preflight-yaml workflows/examples/minimal_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml --phase login
python main.py --run-yaml workflows/examples/minimal_example.yaml --pause-before submit_invoice
python main.py --runs-list
python main.py --runs-show <RUN_ID>
python main.py --logs-show <RUN_ID>
python main.py --report-open <RUN_ID>
```

Adapt workflow names and phase/step IDs to the target workflow.

## Run artifacts

A YAML run creates a folder under `runs/` with operator evidence such as:

- `run_manifest.json` — run index, status, paths, and counts.
- `preflight.json` — blocking errors and warnings before execution.
- `timeline.jsonl` — structured event log for phases, steps, actions, verification, and evidence.
- `records.jsonl` — record status for data-driven workflows.
- `evidence_bundle.json` — failure evidence manifest.
- `repair_packet.json` — compact repair context.
- `report.html` / `report.json` — operator report.

## Debugging order

1. Open `report.html`.
2. Find failed phase and step.
3. Read `failure_kind`.
4. Open `evidence_bundle.json`.
5. Inspect screenshot/DOM/UIA/API/log artifacts.
6. Read failed verification and actual state.
7. Check `safe_retry` before rerunning.
8. Repair workflow/input/selector/config based on evidence.

## Failure routing

- `missing_secret` → configuration/secrets.
- `input_data_error` → input file/Excel contract.
- `selector_not_found` → selector repair and target inspection.
- `verification_failed` → success check mismatch, target rejection, or unexpected state.
- `timeout` → wait policy, wrong condition, slow target.
- `business_rule_rejected` → target accepted automation but rejected the business record.
- `unexpected_state` → target page/window is not where the workflow expected.
