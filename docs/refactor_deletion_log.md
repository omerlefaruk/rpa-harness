# Refactor deletion log

## 2026-06-22 — Secondary store removal slice

Deleted:
- former secondary-store package and service path
- related CLI/config/dashboard/agent/tool/orchestrator/YAML/reporting paths
- related docs, tests, benchmark tool, hidden `.agents` skill/rule
- tracked generated `builder_sessions/` files from Git index
- legacy `tests/rpa` workflow location

Combined:
- runtime truth back to core runner state and run artifacts
- The Automation Challenge workflow under `projects/rpa_challenge/`

Source of truth:
- `timeline.jsonl`
- `run_manifest.json`
- `report.html`
- `evidence_bundle.json`
- `repair_packet.json`

Checks:
- `.venv\Scripts\python.exe -m pytest tests -q` → 316 passed, 7 skipped
- `.venv\Scripts\python.exe -m compileall -q harness tools main.py`
- removed-store `rg` scan → clean
- `git diff --check`

## 2026-06-22 — Dashboard artifact adapter slice

Deleted:
- duplicate run manifest/detail/jsonl readers from `harness/reporting/dashboard.py`

Combined:
- dashboard run artifact reads now call `harness/reporting/run_artifacts.py`

Source of truth:
- `harness/reporting/run_artifacts.py` for run manifest/detail/tail helpers
- dashboard remains the FastAPI presentation adapter

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_workflow_schema.py::test_run_artifact_cli_helpers -q` → 7 passed

## 2026-06-22 — Failure report artifact reader slice

Deleted:
- failure-report artifact reader logic from `harness/reporting/dashboard.py`

Combined:
- dashboard failure report listing now calls `harness/reporting/run_artifacts.py`
- reporting test imports the helper from the artifact module, not the dashboard adapter

Source of truth:
- `harness/reporting/run_artifacts.py` for run/failure artifact readers

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_authoring_reporting.py::test_run_artifacts_collects_failure_metadata -q` → 7 passed

## 2026-06-22 — Local tool-state hygiene slice

Deleted:
- no runtime code; removed future status noise from local tool caches

Combined:
- `.atl/` and `.superpowers/` treated as local generated state in `.gitignore`

Source of truth:
- tracked repo files and committed refactor log; local tool state stays outside Git

Checks:
- `git status --short` shows only real untracked docs/project work after ignore update
- `git diff --check`

## 2026-06-22 — Run-list manifest reader slice

Deleted:
- direct manifest parsing loop from `print_runs_list()`

Combined:
- CLI run list now reuses `collect_run_manifests()` from `harness/reporting/run_artifacts.py`

Source of truth:
- `collect_run_manifests()` for run manifest summary rows

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_cli_summary.py tests/test_dashboard.py tests/test_workflow_schema.py::test_run_artifact_cli_helpers -q` → 11 passed

## 2026-06-22 — Dashboard helper import cleanup

Deleted:
- test import path that treated the dashboard adapter as the artifact-helper source

Combined:
- dashboard tests now import `read_jsonl_tail()` from `harness/reporting/run_artifacts.py`

Source of truth:
- `harness/reporting/run_artifacts.py` for JSONL artifact tailing

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py -q`
