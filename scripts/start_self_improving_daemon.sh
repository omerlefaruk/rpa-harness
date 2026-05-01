#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

: "${PYTHON:=python3}"
: "${AUTORESEARCH_CONFIG:=.autoresearch/autoresearch.sovereign.json}"
: "${AUTORESEARCH_TECH_RADAR:=1}"
: "${AUTORESEARCH_TECH_RADAR_SOURCES_PER_HEARTBEAT:=1}"
export AUTORESEARCH_TECH_RADAR AUTORESEARCH_TECH_RADAR_SOURCES_PER_HEARTBEAT

exec "$PYTHON" main.py --self-improve-24-7 --autoresearch-config "$AUTORESEARCH_CONFIG"
