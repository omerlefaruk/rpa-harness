#!/usr/bin/env bash
set -euo pipefail

start="$(python3 - <<'PY'
import time
print(time.time())
PY
)"

python3 -m py_compile harness/*.py harness/**/*.py main.py tools/autoresearch_runner.py >/dev/null
python3 -m pytest -q tests/test_security.py tests/test_memory.py tests/test_autoresearch_runner.py tests/test_planner.py tests/test_artifact_hygiene.py tests/capabilities/test_reporting_evidence.py tests/capabilities/test_yaml_api_runtime.py >/dev/null

end="$(python3 - <<'PY'
import time
print(time.time())
PY
)"

python3 - <<PY
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
}
score = sum(1 for pattern in required if pattern in patterns)
print(f"METRIC artifact_hygiene_score={score}")
print(f"METRIC default_cli_seconds={end - start:.3f}")
PY
