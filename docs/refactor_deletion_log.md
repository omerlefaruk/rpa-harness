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

## 2026-06-22 — Selector repair artifact reader slice

Deleted:
- local JSON artifact reader from `harness/selectors/repair.py`

Combined:
- selector repair now reads repair/evidence artifacts through `harness/reporting/run_artifacts.py`

Source of truth:
- `read_json()` in `harness/reporting/run_artifacts.py`

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_authoring_reporting.py::test_production_selector_repair_requires_validated_candidate_and_approval tests/test_authoring_reporting.py::test_selector_repair_plan_contains_swarm_command -q` → 2 passed

## 2026-06-22 — Observability artifact reader slice

Deleted:
- local JSON and JSONL artifact readers from `harness/observability.py`
- duplicate JSONL tail parsing loop in `read_jsonl_tail()`

Combined:
- observability indexing now uses `read_json()` and `read_jsonl()` from `harness/reporting/run_artifacts.py`
- JSONL tailing now delegates to the full JSONL reader

Source of truth:
- `harness/reporting/run_artifacts.py` for JSON/JSONL run artifact reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_operator_layer.py::test_observability_indexes_runs_idempotently_and_redacts tests/capabilities/test_desktop_evidence_store.py::test_observability_indexes_desktop_evidence_artifacts tests/test_dashboard.py tests/test_cli_summary.py -q` → 12 passed

## 2026-06-22 — Copilot JSONL reader slice

Deleted:
- local JSONL reader from `harness/copilot_session.py`

Combined:
- copilot session question/answer reads now use `read_jsonl()` from `harness/reporting/run_artifacts.py`

Source of truth:
- `harness/reporting/run_artifacts.py` for JSONL artifact/session reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py tests/test_dashboard.py::test_dashboard_exposes_copilot_sessions -q` → 12 passed

## 2026-06-22 — YAML runner report reader slice

Deleted:
- local JSON and JSONL report artifact readers from `harness/rpa/yaml_runner.py`

Combined:
- YAML runner report generation now uses `read_json()` and `read_jsonl()` from `harness/reporting/run_artifacts.py`

Source of truth:
- `harness/reporting/run_artifacts.py` for report artifact reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/test_workflow_schema.py::test_yaml_runner_failed_run_artifacts_are_redacted tests/capabilities/test_rpa_workflow_capabilities.py -q` → 14 passed

## 2026-06-22 — Desktop AI JSON reader slice

Deleted:
- local dict JSON reader from `harness/desktop/ai_controller.py`

Combined:
- desktop AI proposal reads now use `read_json()` from `harness/reporting/run_artifacts.py`

Source of truth:
- `harness/reporting/run_artifacts.py` for dict JSON reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/capabilities/test_desktop_ai_controller.py tests/capabilities/test_desktop_evidence_store.py -q` → 7 passed

## 2026-06-22 — Core artifact IO boundary slice

Deleted:
- reverse dependency from runtime/core consumers to `harness/reporting/run_artifacts.py` for artifact IO
- duplicated artifact IO ownership inside the reporting facade

Combined:
- shared artifact IO helpers moved to `harness/core/artifacts.py`
- reporting, dashboard, observability, selector repair, copilot, YAML runner, and desktop AI consume the core helper

Source of truth:
- `harness/core/artifacts.py` for artifact path/JSON/JSONL reads
- `harness/reporting/run_artifacts.py` remains the reporting/CLI facade

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_authoring_reporting.py tests/test_cli_summary.py tests/test_operator_layer.py::test_observability_indexes_runs_idempotently_and_redacts tests/test_workflow_schema.py::test_yaml_runner_failed_run_artifacts_are_redacted tests/test_copilot_session.py tests/capabilities/test_desktop_ai_controller.py -q` → 35 passed

## 2026-06-22 — OKF artifact IO note

Deleted:
- no runtime code

Combined:
- durable runtime knowledge now names `harness.core.artifacts` as the shared artifact IO source

Source of truth:
- `docs/okf/runtime/workflow-runner.md` for durable runtime knowledge

Checks:
- `.venv\Scripts\python.exe scripts/okf.py validate docs/okf`
