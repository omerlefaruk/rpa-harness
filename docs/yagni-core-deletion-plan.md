# YAGNI Core Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `rpa-harness` to a terminal-first, YAML-runner-only core by deleting duplicate runtimes, duplicate UI surfaces, unused optional layers, and unused dependencies.

**Architecture:** `harness/rpa/yaml_runner.py` becomes the only execution source of truth. Run artifacts (`timeline.jsonl`, `run_manifest.json`, `report.html`, `report.json`, `failure_report.json`, `evidence_bundle.json`, `repair_packet.json`) remain the durable evidence surface. Terminal commands and artifact readers replace dashboard/frontend/SQLite surfaces.

**Tech Stack:** Python stdlib, PyYAML, Playwright, OpenPyXL, existing YAML runner, existing run artifacts.

---

## Guardrails

- Keep YAML workflow execution working at every commit.
- Do not delete input validation, redaction, success checks, evidence capture, or credential policy.
- Do not mix this refactor with existing untracked `projects/bizimhesap/` artifacts unless the user explicitly wants them included.
- Commit after each phase.
- Prefer deletion over replacement. Add code only when a deleted surface needs a tiny terminal equivalent.

## Current deletion targets

- Delete Python class runtime path: `harness/rpa/workflow.py`, `harness/orchestrator.py`, class runtime CLI flags/tests.
- Delete frontend/dashboard surfaces: `frontend/`, `harness/reporting/dashboard.py`, dashboard tests/docs.
- Delete duplicated Rezervasyon workflow clones.
- Delete historical plan docs: `docs/superpowers/plans/`.
- Delete unused local subagents and config.
- Delete unused Office/PDF layer and deps.
- Delete fixture-only job queue.
- Drop unused deps: `pydantic`, `pydantic-settings`, `aiofiles`, `jinja2`, `jsonpath-ng`, `python-docx`, `pypdf`.
- Delete SQLite observability index and scan run artifacts on demand.

---

## Phase 0: Safety snapshot

**Files:**
- Read: repository status only.

- [ ] **Step 1: Inspect current working tree**

```powershell
git status --short --untracked-files=all
```

Expected: show existing dirty files so this refactor does not accidentally claim unrelated work.

- [ ] **Step 2: Create branch**

```powershell
git switch -c codex/yagni-core-deletion
```

Expected: branch created.

---

## Phase 1: Delete frontend and dashboard surfaces

**Files:**
- Delete: `frontend/`
- Delete: `harness/reporting/dashboard.py`
- Delete: `tests/test_dashboard.py`
- Delete: `tests/test_react_dashboard_contract.py`
- Delete: `docs/react_dashboard.md`
- Delete: `docs/live_ui.md`
- Modify: `harness/cli.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: tests importing `create_dashboard`

- [ ] **Step 1: Remove dashboard CLI and imports**

Remove `--serve`, `--port`, and dashboard startup branches from `harness/cli.py`.

- [ ] **Step 2: Delete dashboard/frontend files**

```powershell
Remove-Item -Recurse -Force frontend
Remove-Item -Force harness/reporting/dashboard.py
Remove-Item -Force tests/test_dashboard.py
Remove-Item -Force tests/test_react_dashboard_contract.py
Remove-Item -Force docs/react_dashboard.md
Remove-Item -Force docs/live_ui.md
```

- [ ] **Step 3: Remove dashboard dependencies**

Remove from `pyproject.toml` and `uv.lock`:

```text
fastapi
uvicorn
jinja2
```

- [ ] **Step 4: Run focused checks**

```powershell
python -m pytest tests/test_cli_summary.py tests/test_operator_layer.py -q
python -m compileall -q harness
```

Expected: tests pass or only fail where they still reference deleted dashboard behavior.

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "refactor: delete dashboard surfaces"
```

---

## Phase 2: Make YAML runner the only runtime

**Files:**
- Keep: `harness/rpa/yaml_runner.py`
- Delete: `harness/rpa/workflow.py`
- Delete: `harness/orchestrator.py`
- Delete: `harness/test_case.py`
- Delete or rewrite: class-runtime tests under `tests/capabilities/test_harness_discovery.py`
- Modify: `harness/__init__.py`
- Modify: `harness/cli.py`
- Modify: `README.md`
- Modify: `docs/okf/*`

- [ ] **Step 1: Remove class-runtime CLI flags**

Remove these flags and branches from `harness/cli.py`:

```text
--discover
--discover-wf
--run
--run-workflows
--agent
--test-name
--workflow-name
```

- [ ] **Step 2: Delete Python runtime modules**

```powershell
Remove-Item -Force harness/rpa/workflow.py
Remove-Item -Force harness/orchestrator.py
Remove-Item -Force harness/test_case.py
```

- [ ] **Step 3: Simplify public exports**

Update `harness/__init__.py` to export only YAML/core pieces that still exist. Keep it boring; no compatibility re-export layer.

- [ ] **Step 4: Remove or convert class-runtime tests**

Delete tests that only prove dynamic class discovery or `AutomationTestCase` execution. Convert only tests that protect YAML runner behavior.

- [ ] **Step 5: Run YAML-focused checks**

```powershell
python -m pytest tests/test_workflow_schema.py tests/capabilities/test_yaml_api_runtime.py tests/capabilities/test_yaml_browser_runtime.py tests/capabilities/test_yaml_excel_desktop_runtime.py tests/test_verification.py -q
python -m compileall -q harness
```

Expected: YAML runner, verification, and artifacts still work.

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: make yaml runner the only runtime"
```

---

## Phase 3: Remove duplicated Rezervasyon workflow clones

**Files:**
- Delete: `projects/rezervasyon_puan_reviews/_ota_link_swarm_from_excel.py`
- Delete: `projects/rezervasyon_puan_reviews/_trip_com_reviews_from_excel.py`
- Delete: `projects/rezervasyon_puan_reviews/_trip_review_tools.py`
- Delete: `projects/rezervasyon_puan_reviews/_review_collector.py`
- Modify: `projects/rezervasyon_puan_reviews/workflow.py`

- [ ] **Step 1: Replace private clone imports with canonical modules**

In `projects/rezervasyon_puan_reviews/workflow.py`, import from canonical project modules instead of private cloned files:

```text
projects/ota_link_swarm/workflow.py
projects/trip_com_reviews/workflow.py
projects/ota_recent_reviews/workflow.py
tests/browser/trip_marmara_taksim_reviews.py
```

- [ ] **Step 2: Delete clone files**

```powershell
Remove-Item -Force projects/rezervasyon_puan_reviews/_ota_link_swarm_from_excel.py
Remove-Item -Force projects/rezervasyon_puan_reviews/_trip_com_reviews_from_excel.py
Remove-Item -Force projects/rezervasyon_puan_reviews/_trip_review_tools.py
Remove-Item -Force projects/rezervasyon_puan_reviews/_review_collector.py
```

- [ ] **Step 3: Run project checks**

```powershell
python -m pytest projects/rezervasyon_puan_reviews/tests projects/ota_link_swarm/tests projects/trip_com_reviews/tests projects/ota_recent_reviews/tests -q
```

Expected: project helper behavior still passes.

- [ ] **Step 4: Commit**

```powershell
git add -A
git commit -m "refactor: remove duplicated rezervasyon workflow code"
```

---

## Phase 4: Delete unused optional layers and dependencies

**Files:**
- Delete: `subagents/`
- Delete: `harness/rpa/office.py`
- Delete: `harness/rpa/queue.py`
- Delete: `harness/resilience/healing.py`
- Delete: `harness/rpa/retry.py`
- Modify: `harness/config.py`
- Modify: `conftest.py`
- Modify: `harness/verification/checks.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Remove unused subagent config**

Delete `SubagentConfig`, `subagents`, and `get_subagent_config()` from `harness/config.py`.

- [ ] **Step 2: Delete dead optional modules**

```powershell
Remove-Item -Recurse -Force subagents
Remove-Item -Force harness/rpa/office.py
Remove-Item -Force harness/rpa/queue.py
Remove-Item -Force harness/resilience/healing.py
Remove-Item -Force harness/rpa/retry.py
```

- [ ] **Step 3: Remove job queue fixture**

Delete the `job_queue` fixture from `conftest.py`.

- [ ] **Step 4: Force stdlib/basic JSONPath**

In `harness/verification/checks.py`, remove the optional `jsonpath_ng.ext.parse` import path and always use `_resolve_basic_json_path()`.

- [ ] **Step 5: Remove unused dependencies**

Remove from `pyproject.toml` and `uv.lock`:

```text
pydantic
pydantic-settings
aiofiles
python-docx
pypdf
jsonpath-ng
```

- [ ] **Step 6: Run focused checks**

```powershell
python -m pytest tests/test_verification.py tests/test_config.py tests/test_selector_strategy.py -q
python -m compileall -q harness
```

Expected: verification and config still work without removed dependencies.

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "refactor: delete unused optional layers"
```

---

## Phase 5: Remove SQLite observability index

**Files:**
- Delete: `harness/observability.py`
- Modify: `harness/cli.py`
- Modify: `harness/reporting/run_artifacts.py`
- Modify: observability tests/docs.

- [ ] **Step 1: Remove observability CLI flags**

Remove these flags and branches from `harness/cli.py`:

```text
--observability-index
--observability-rebuild
--observability-stats
--observability-db-path
--observability-db
```

- [ ] **Step 2: Delete SQLite observability module**

```powershell
Remove-Item -Force harness/observability.py
```

- [ ] **Step 3: Use artifact scanning instead**

Keep run listing/show/log/report commands backed by `harness/reporting/run_artifacts.py`. If a deleted observability command had a terminal use case, route it to existing run artifact readers instead of adding a database replacement.

- [ ] **Step 4: Remove observability docs/tests**

Delete docs and tests that exist only to prove SQLite indexing. Keep tests that prove run artifact reading.

- [ ] **Step 5: Run focused checks**

```powershell
python -m pytest tests/test_cli_summary.py tests/test_workflow_schema.py tests/test_authoring_reporting.py -q
python -m compileall -q harness
```

Expected: terminal artifact commands still work.

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: use run artifacts instead of observability db"
```

---

## Phase 6: Docs and OKF cleanup

**Files:**
- Delete: `docs/superpowers/plans/`
- Modify: `README.md`
- Modify: `docs/okf/*`
- Modify: docs that still mention dashboard, Python class runtime, SQLite observability, subagents, Office/PDF, or JobQueue.

- [ ] **Step 1: Delete historical plan docs**

```powershell
Remove-Item -Recurse -Force docs/superpowers/plans
```

- [ ] **Step 2: Update terminal-only docs**

Update docs to say:

```text
YAML workflows are the only supported runtime.
Operators use terminal commands and run artifacts.
Run artifacts are the source of truth.
No dashboard, React frontend, SQLite observability DB, class workflow runtime, local subagent framework, Office/PDF layer, or job queue is part of the core.
```

- [ ] **Step 3: Refresh OKF indexes**

```powershell
python scripts/okf.py generate-indexes docs/okf
python scripts/okf.py validate docs/okf
```

Expected: OKF validation passes.

- [ ] **Step 4: Run final checks**

```powershell
python -m pytest -q
python -m compileall -q harness scripts tools
git diff --check
```

Expected: full suite passes; no whitespace errors.

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "docs: document terminal-only yaml core"
```

---

## Final acceptance

- [ ] `rg "frontend|dashboard|observability|SubagentConfig|JobQueue|OfficeHandler|RPAWorkflow|AutomationHarness" harness tests docs README.md pyproject.toml uv.lock` returns only intentional historical mentions.
- [ ] `python -m pytest -q` passes.
- [ ] `python -m compileall -q harness scripts tools` passes.
- [ ] `git diff --check` passes.
- [ ] `pyproject.toml` and `uv.lock` agree.

## Expected net cut

- Approximately `-9k` lines.
- Removes frontend npm stack.
- Removes roughly seven Python dependencies.
- Leaves a smaller terminal-first YAML automation core.
