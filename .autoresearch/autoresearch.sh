#!/usr/bin/env bash
set -euo pipefail

python_bin="${PYTHON:-python3}"
start="$($python_bin -c 'import time; print(time.time())')"

mapfile -t py_files < <(find harness subagents tools tests -name '*.py' -print | sort)
"$python_bin" -m py_compile main.py conftest.py "${py_files[@]}" >/dev/null
"$python_bin" -m pytest -q \
  tests/test_security.py \
  tests/test_memory.py \
  tests/test_autoresearch_runner.py \
  tests/test_autoresearch_supervisor.py \
  tests/test_planner.py \
  tests/test_artifact_hygiene.py \
  tests/test_project_metadata.py \
  tests/test_line_endings.py \
  tests/test_tech_radar.py \
  tests/capabilities/test_reporting_evidence.py \
  tests/capabilities/test_yaml_api_runtime.py >/dev/null

end="$($python_bin -c 'import time; print(time.time())')"

"$python_bin" - <<PY
from pathlib import Path

start = float("$start")
end = float("$end")
patterns = set(Path(".gitignore").read_text().splitlines())
required = {
    "reports/",
    "runs/*",
    "!runs/.gitkeep",
    "screenshots/",
    "downloads/",
    "logs/",
    "data/*.xlsx",
    "data/*.csv",
    "data/*.db",
    "data/*.db-*",
    "data/*.sqlite",
    "data/*.sqlite-*",
    ".env",
    ".env.local",
    "playwright-report/",
    "test-results/",
    ".autoresearch/worktrees/",
    ".autoresearch/supervisor.jsonl",
    ".autoresearch/supervisor_plan.md",
    ".autoresearch/review.md",
    ".autoresearch/review.json",
    ".autoresearch/autoresearch.learnings.md",
    ".autoresearch/tech_radar.state.json",
    ".autoresearch/tech_radar.jsonl",
    ".autoresearch/tech_radar_candidates.md",
}
score = sum(1 for pattern in required if pattern in patterns)
print(f"METRIC artifact_hygiene_score={score}")
print(f"METRIC default_cli_seconds={end - start:.3f}")
PY
