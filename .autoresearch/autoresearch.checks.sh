#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile harness/*.py harness/**/*.py main.py tools/autoresearch_runner.py
python3 -m pytest -q tests/test_security.py tests/test_memory.py tests/test_autoresearch_runner.py
