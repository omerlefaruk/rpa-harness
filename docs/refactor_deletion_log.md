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
