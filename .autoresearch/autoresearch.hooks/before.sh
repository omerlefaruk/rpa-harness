#!/usr/bin/env bash
set -euo pipefail

payload="$(cat)"
session_dir=".autoresearch"
audit_path="$session_dir/supervisor.jsonl"
ideas_path="$session_dir/autoresearch.ideas.md"

echo "Autoresearch before-hook context"

if [[ -s "$ideas_path" ]]; then
  echo
  echo "Open idea backlog:"
  grep -E '^- \[ \]' "$ideas_path" | head -5 || true
fi

if [[ -s "$audit_path" ]]; then
  recent_rejections="$(
    tail -20 "$audit_path" \
      | grep -E '"status": "(agent_failed|experiment_rejected|review_failed|review_blocked|low_confidence|checks_failed)"' \
      | tail -3 \
      | wc -l \
      | tr -d ' '
  )"
  if [[ "$recent_rejections" == "3" ]]; then
    echo
    echo "Anti-thrash: last cycles repeatedly rejected work. Choose a different failure class or a smaller deterministic change."
  fi
fi

if [[ -n "$payload" ]]; then
  echo
  echo "Candidate payload received."
fi
