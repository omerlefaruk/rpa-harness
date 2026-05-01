#!/usr/bin/env bash
set -euo pipefail

python_bin="${PYTHON:-python3}"
mapfile -t py_files < <(find harness subagents tools tests -name '*.py' -print | sort)
"$python_bin" -m py_compile main.py conftest.py "${py_files[@]}"
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
  tests/capabilities/test_yaml_api_runtime.py
