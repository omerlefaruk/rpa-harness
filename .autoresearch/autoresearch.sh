#!/usr/bin/env bash
set -euo pipefail

start="$(python3 - <<'PY'
import time
print(time.time())
PY
)"

python3 -m py_compile harness/*.py harness/**/*.py main.py >/dev/null
python3 -m pytest -q tests/test_security.py tests/test_memory.py tests/test_autoresearch_runner.py >/dev/null

end="$(python3 - <<'PY'
import time
print(time.time())
PY
)"

python3 - <<PY
start = float("$start")
end = float("$end")
print("METRIC capability_pass_rate=1")
print(f"METRIC default_cli_seconds={end - start:.3f}")
PY
