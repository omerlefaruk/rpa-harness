"""Shared helpers for reading run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_dir_for_id(runs_dir: Path, run_id: str) -> Path:
    safe_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in run_id)
    return runs_dir / safe_id


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def read_jsonl_tail(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    return read_jsonl(path)[-limit:]
