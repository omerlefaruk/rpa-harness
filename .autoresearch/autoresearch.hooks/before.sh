#!/usr/bin/env bash
set -euo pipefail

payload="$(cat)"
session_dir=".autoresearch"
audit_path="$session_dir/supervisor.jsonl"
ideas_path="$session_dir/autoresearch.ideas.md"
tech_config="$session_dir/tech_radar.sources.json"

echo "Autoresearch before-hook context"

if [[ -s "$ideas_path" ]]; then
  echo
  echo "Open idea backlog:"
  grep -E '^- \[ \]' "$ideas_path" | head -5 || true
fi

if [[ "${AUTORESEARCH_TECH_RADAR:-1}" != "0" && -f tools/tech_radar.py && -f "$tech_config" ]]; then
  tech_timeout="${AUTORESEARCH_TECH_RADAR_WALL_TIMEOUT:-15}"
  tech_python="${PYTHON:-python3}"
  tech_cmd=(
    "$tech_python" tools/tech_radar.py
    --config "$tech_config"
    --state "$session_dir/tech_radar.state.json"
    --jsonl "$session_dir/tech_radar.jsonl"
    --candidates "$session_dir/tech_radar_candidates.md"
    --timeout "${AUTORESEARCH_TECH_RADAR_TIMEOUT:-8}"
    --cycle-size "${AUTORESEARCH_TECH_RADAR_SOURCES_PER_HEARTBEAT:-1}"
  )
  if command -v timeout >/dev/null 2>&1; then
    tech_cmd=(timeout "$tech_timeout" "${tech_cmd[@]}")
  fi
  tech_output="$(${tech_cmd[@]} 2>/dev/null || true)"
  if [[ -n "$tech_output" ]]; then
    echo
    echo "Technology radar heartbeat:"
    echo "$tech_output" | tail -20
  fi
  if [[ -s "$session_dir/tech_radar_candidates.md" ]]; then
    echo
    echo "Recent technology radar candidates:"
    grep -E '^- \[ \]' "$session_dir/tech_radar_candidates.md" | tail -5 || true
  fi
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
