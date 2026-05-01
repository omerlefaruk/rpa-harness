#!/usr/bin/env bash
set -euo pipefail

payload="$(cat)"
session_dir=".autoresearch"
learnings_path="$session_dir/autoresearch.learnings.md"
mkdir -p "$session_dir"

status="$(
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("status", "unknown"))' <<<"$payload" 2>/dev/null \
  || printf 'unknown'
)"
commit="$(
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("commit", ""))' <<<"$payload" 2>/dev/null \
  || true
)"
timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if [[ -n "$commit" ]]; then
  printf -- "- %s status=%s commit=%s\n" "$timestamp" "$status" "$commit" >> "$learnings_path"
else
  printf -- "- %s status=%s\n" "$timestamp" "$status" >> "$learnings_path"
fi
