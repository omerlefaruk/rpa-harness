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

## 2026-06-22 — CLI shim cleanup slice

Deleted:
- internal helper re-exports from `main.py`
- test imports that treated the compatibility shim as the helper source

Combined:
- tests now import CLI helpers directly from `harness/cli.py`

Source of truth:
- `harness/cli.py` for CLI helpers
- `main.py` only delegates to `harness.cli.run()`

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_cli_summary.py tests/test_config.py tests/test_telegram_notifications.py tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/test_cli_entrypoint.py -q` → 22 passed

## 2026-06-22 — Run artifact facade cleanup slice

Deleted:
- direct `json.loads(...read_text...)` manifest parsing in `harness/reporting/run_artifacts.py`
- local JSONL record parsing loop in `latest_records()`

Combined:
- run list, manifest print, retry manifest read, and latest-record reads now reuse core artifact readers

Source of truth:
- `harness/core/artifacts.py` for JSON and JSONL artifact reads
- `harness/reporting/run_artifacts.py` remains the CLI/reporting facade

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/test_cli_summary.py -q` → 5 passed

## 2026-06-22 — Dashboard safe-path helper slice

Deleted:
- duplicate safe child path implementations for run artifacts and workspace files in `harness/reporting/dashboard.py`

Combined:
- artifact and workflow graph endpoints now share one `_safe_child_path()` helper

Source of truth:
- `_safe_child_path()` in `harness/reporting/dashboard.py` for dashboard-local path containment checks

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py -q` → 6 passed

## 2026-06-22 — YAML runner record summary reader slice

Deleted:
- local JSONL parsing loop in `YamlWorkflowRunner._record_summary()`

Combined:
- YAML runner record summary now reads records through the core JSONL artifact helper

Source of truth:
- `harness/core/artifacts.py` for JSONL artifact reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_workflow_schema.py::test_yaml_runner_failed_run_artifacts_are_redacted tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/capabilities/test_rpa_workflow_capabilities.py -q` → 14 passed

## 2026-06-22 — Resume ledger reader slice

Deleted:
- local JSONL parsing loop in `ResumeLedger.latest_by_record()`

Combined:
- resume ledger reads now use the core JSONL artifact helper

Source of truth:
- `harness/core/artifacts.py` for JSONL reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_authoring_reporting.py::test_resume_ledger_records_latest_status tests/capabilities/test_rpa_workflow_capabilities.py -q` → 13 passed

## 2026-06-22 — Copilot discovery cache reader slice

Deleted:
- local JSON decode/error handling in `_read_discovery_cache()`

Combined:
- copilot discovery cache reads now use the core JSON artifact helper

Source of truth:
- `harness/core/artifacts.py` for JSON artifact reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py -q` → 11 passed

## 2026-06-22 — Reporting facade export cleanup slice

Deleted:
- reporting facade re-exports for core artifact IO helpers from `harness/reporting/run_artifacts.py`
- test import that treated reporting as the source for `read_jsonl_tail()`

Combined:
- callers that need core artifact IO now import it from `harness/core/artifacts.py`

Source of truth:
- `harness/core/artifacts.py` for artifact IO helpers
- `harness/reporting/run_artifacts.py` only exposes reporting/CLI run helpers

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/test_cli_summary.py -q` → 11 passed

## 2026-06-22 — Builder JSON reader slice

Deleted:
- local JSON reader from `harness/builder.py`

Combined:
- builder JSON reads now use `harness/core/artifacts.py`
- core `read_json()` keeps dict-default behavior and supports explicit defaults for existing list-valued builder files

Source of truth:
- `harness/core/artifacts.py` for JSON artifact/file reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py::test_dashboard_exposes_runs_and_builder_sessions tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/test_copilot_session.py::test_start_copilot_session_creates_redacted_state -q` → 3 passed

## 2026-06-22 — Workflow ID slug helper slice

Deleted:
- duplicate workflow ID slug helpers from `harness/dsl.py` and `harness/rpa/schema.py`

Combined:
- DSL compilation and legacy schema migration now share `slug_id()` from core

Source of truth:
- `harness/core/ids.py` for workflow-safe identifier slugs

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dsl.py tests/test_operator_layer.py::test_migrate_legacy_workflow_preserves_success_checks_and_redacts -q` → 6 passed

## 2026-06-22 — Workflow ID validator slice

Deleted:
- duplicate workflow-safe ID regex definitions from schema and verification contract modules

Combined:
- schema validation and verification contract validation now share `WORKFLOW_ID_RE` from core

Source of truth:
- `harness/core/ids.py` for workflow-safe ID creation and validation rules

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dsl.py tests/test_operator_layer.py::test_default_schema_validates_and_generates_graph tests/test_operator_layer.py::test_default_schema_rejects_missing_success_check_and_unsafe_retry tests/test_workflow_schema.py::test_validate_minimal_workflow tests/test_workflow_schema.py::test_validate_yaml_cli_outputs_workflow_summary tests/test_verification.py::test_validate_workflow_missing_fields tests/test_verification.py::test_validate_workflow_valid -q` → 11 passed

## 2026-06-22 — Evidence bundle JSON reader slice

Deleted:
- direct `json.loads(...read_text...)` failure-report parsing in `harness/reporting/evidence_bundle.py`

Combined:
- evidence bundle manifest generation now reads `failure_report.json` through the core JSON artifact helper

Source of truth:
- `harness/core/artifacts.py` for JSON artifact reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_authoring_reporting.py::test_failure_report_html_and_evidence_bundle -q` → 1 passed

## 2026-06-22 — Session ID sanitizer slice

Deleted:
- builder-owned `safe_session_id()` implementation used by both builder and copilot session code

Combined:
- builder and copilot session paths now share the core ID sanitizer

Source of truth:
- `harness/core/ids.py` for session-safe IDs

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py::test_dashboard_exposes_runs_and_builder_sessions tests/test_dashboard.py::test_dashboard_exposes_copilot_sessions tests/test_copilot_session.py::test_start_copilot_session_creates_redacted_state tests/test_copilot_session.py::test_run_copilot_try_url_creates_task_and_report -q` → 4 passed

## 2026-06-22 — Python workflow live report reader slice

Deleted:
- direct `json.loads(...read_text...)` manifest read in `Workflow._write_live_report()`

Combined:
- Python workflow live report generation now reads `run_manifest.json` through the core JSON artifact helper

Source of truth:
- `harness/core/artifacts.py` for run manifest JSON reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/capabilities/test_rpa_workflow_capabilities.py::test_python_rpa_workflow_writes_live_dashboard_artifacts -q` → 1 passed

## 2026-06-22 — Required JSON reader slice

Deleted:
- direct required `json.loads(...read_text...)` JSON reads from autopilot command manifest, copilot state, and failure HTML rendering
- now-unused JSON imports in `harness/autopilot.py` and `harness/reporting/failure_html.py`

Combined:
- required JSON file reads now share `read_required_json()` from core while preserving fail-fast behavior for missing or invalid files

Source of truth:
- `harness/core/artifacts.py` for optional and required JSON artifact/file reads

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_autopilot.py::test_autopilot_policy_and_command_manifest_are_agent_readable tests/test_copilot_session.py::test_start_copilot_session_creates_redacted_state tests/test_authoring_reporting.py::test_failure_report_html_and_evidence_bundle -q` → 3 passed

## 2026-06-22 — Secret reference regex slice

Deleted:
- duplicate `${secrets.NAME}` regex definitions from schema, verification contract, and YAML runner modules

Combined:
- schema validation, verification contract validation, and YAML runtime interpolation now use the shared security secret-reference pattern

Source of truth:
- `harness/security.py` for secret reference parsing/redaction primitives

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_workflow_schema.py::test_validate_secret_reference_must_be_declared tests/test_workflow_schema.py::test_validate_rejects_secret_in_inputs tests/test_verification.py::test_validate_workflow_missing_fields tests/test_verification.py::test_validate_workflow_valid tests/test_workflow_schema.py::test_yaml_runner_failed_run_artifacts_are_redacted tests/test_security.py -q` → 10 passed

## 2026-06-22 — Input reference regex slice

Deleted:
- duplicate `${inputs.NAME}` regex definitions from verification contract and YAML runner modules

Combined:
- validation and runtime interpolation now share the core input-reference pattern

Source of truth:
- `harness/core/ids.py` for workflow ID and input-reference identifier rules

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_workflow_schema.py::test_yaml_runner_workflow_inputs_override_default_config_variables tests/test_verification.py::test_validate_workflow_valid tests/capabilities/test_yaml_schema_edges.py::test_valid_browser_api_and_no_op_workflows_validate -q` → 3 passed

## 2026-06-22 — Redaction sentinel slice

Deleted:
- duplicated `[REDACTED]` sentinel literals from verification, notification, and YAML runtime consumers

Combined:
- consumers now use the shared `REDACTED` value from security

Source of truth:
- `harness/security.py` for redaction sentinel and redaction primitives

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_verification.py::test_success_check_redacted tests/test_verification.py::test_check_runner_redacted tests/test_bot_notifications.py::test_bot_notifier_routes_failure_and_redacts_context tests/test_workflow_schema.py::test_yaml_runner_failed_run_artifacts_are_redacted tests/capabilities/test_yaml_api_runtime.py::test_api_response_context_sanitizes_url_headers_and_body -q` → 5 passed

## 2026-06-22 — Redacted JSON writer slice

Deleted:
- builder-owned redacted JSON writer implementation
- desktop AI direct redacted JSON write implementation

Combined:
- builder and desktop AI now write redacted JSON through the core artifact writer

Source of truth:
- `harness/core/artifacts.py` for JSON artifact reads and writes

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_dashboard.py::test_dashboard_exposes_runs_and_builder_sessions tests/test_workflow_schema.py::test_run_artifact_cli_helpers tests/capabilities/test_desktop_ai_controller.py -q` → 7 passed

## 2026-06-22 — UTC timestamp helper slice

Deleted:
- duplicate UTC ISO `_now()` implementations from copilot, copilot sessions, Python workflow, and YAML runner code

Combined:
- runtime and copilot timestamp reads now use one core helper

Source of truth:
- `harness/core/time.py` for UTC ISO timestamps

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py::test_start_copilot_session_creates_redacted_state tests/test_copilot_session.py::test_answer_copilot_question_records_answer_and_advances tests/test_workflow_schema.py::test_yaml_runner_failed_run_artifacts_are_redacted tests/capabilities/test_rpa_workflow_capabilities.py::test_python_rpa_workflow_writes_live_dashboard_artifacts -q` → 4 passed

## 2026-06-22 — Remaining UTC timestamp writer slice

Deleted:
- direct UTC ISO timestamp calls from builder metadata, JSONL logging, resume ledger entries, and failure report entries

Combined:
- remaining timestamp writers now use the core UTC helper

Source of truth:
- `harness/core/time.py` for UTC ISO timestamps

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_logger.py tests/test_authoring_reporting.py::test_resume_ledger_records_latest_status tests/capabilities/test_reporting_evidence.py::test_failure_report_writes_redacted_evidence_bundle tests/test_dashboard.py::test_dashboard_exposes_runs_and_builder_sessions -q` → 4 passed
- `.venv\Scripts\python.exe -m compileall -q harness\builder.py harness\logger.py harness\rpa\ledger.py harness\reporting\failure_report.py` → passed
- `git diff --check` → passed
- `rg -n "datetime\.now\(timezone\.utc\)\.isoformat\(\)" harness --glob '!harness/core/time.py' -S` → no matches

## 2026-06-22 — JSON reporter writer slice

Deleted:
- JSONReporter's local redacted JSON file writer

Combined:
- test/report JSON output now uses the core redacted JSON artifact writer

Source of truth:
- `harness/core/artifacts.py` for redacted JSON writes

Checks:
- `.venv\Scripts\python.exe -m pytest tests/capabilities/test_reporting_evidence.py::test_json_report_includes_test_and_workflow_metadata tests/capabilities/test_reporting_evidence.py::test_json_report_redacts_secret_like_log_values -q` → 2 passed
- `.venv\Scripts\python.exe -m compileall -q harness\reporting\__init__.py` → passed
- `git diff --check` → passed


## 2026-06-22 — Failure report JSON writer slice

Deleted:
- failure report local redacted JSON write paths for `repair_packet.json`, `evidence_bundle.json`, and `failure_report.json`

Combined:
- failure evidence JSON surfaces now use the core redacted JSON writer

Source of truth:
- `harness/core/artifacts.py` for redacted JSON writes

Checks:
- `.venv\Scripts\python.exe -m pytest tests/capabilities/test_reporting_evidence.py::test_failure_report_includes_repro_command_and_evidence_paths tests/capabilities/test_reporting_evidence.py::test_failure_report_writes_redacted_evidence_bundle tests/capabilities/test_reporting_evidence.py::test_failure_report_includes_rulebook_failure_fields tests/test_repair_loop.py -q` → 9 passed
- `.venv\Scripts\python.exe -m compileall -q harness\reporting\failure_report.py` → passed
- `git diff --check` → passed


## 2026-06-22 — API response JSON writer slice

Deleted:
- API driver's local redacted JSON response artifact writer

Combined:
- API response artifacts now use the core redacted JSON writer

Source of truth:
- `harness/core/artifacts.py` for redacted JSON writes

Checks:
- inline APIDriver screenshot check with a fake JSON response → passed
- `.venv\Scripts\python.exe -m pytest tests/capabilities/test_yaml_api_runtime.py::test_authorization_secret_is_used_but_not_leaked_in_result tests/capabilities/test_yaml_api_runtime.py::test_api_failure_report_has_sanitized_redacted_response_preview tests/capabilities/test_yaml_api_runtime.py::test_api_response_context_sanitizes_url_headers_and_body -q` → 3 passed
- `.venv\Scripts\python.exe -m compileall -q harness\drivers\api.py` → passed
- `.venv\Scripts\python.exe -m pytest tests/test_line_endings.py::test_repository_text_files_use_lf_line_endings -q` → 1 passed
- `git diff --check` → passed


## 2026-06-22 — Selector repair decision writer slice

Deleted:
- selector repair's local redacted JSON decision writer

Combined:
- `selector_repair_decision.json` now uses the core redacted JSON writer

Source of truth:
- `harness/core/artifacts.py` for redacted JSON writes

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_authoring_reporting.py::test_production_selector_repair_requires_validated_candidate_and_approval tests/test_authoring_reporting.py::test_selector_repair_plan_contains_swarm_command -q` → 2 passed
- `.venv\Scripts\python.exe -m compileall -q harness\selectors\repair.py` → passed
- `git diff --check` → passed


## 2026-06-22 — Copilot discovery cache writer slice

Deleted:
- copilot discovery cache's local redacted JSON writer

Combined:
- copilot discovery cache JSON now uses the core redacted JSON writer

Source of truth:
- `harness/core/artifacts.py` for redacted JSON writes

Checks:
- `.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py::test_advance_copilot_session_reuses_discovery_cache tests/test_copilot_session.py::test_copilot_cli_outputs_json tests/test_copilot_session.py::test_copilot_auto_cli_reaches_review_with_json_only tests/test_dashboard.py::test_dashboard_exposes_copilot_sessions -q` → 4 passed
- `.venv\Scripts\python.exe -m compileall -q harness\copilot_session.py` → passed
- `git diff --check` → passed
