"""Shared helpers for reading run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.security import redact_value


def run_dir_for_id(runs_dir: Path, run_id: str) -> Path:
    safe_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in run_id)
    return runs_dir / safe_id


def read_json(path: Path, default: Any = None) -> Any:
    fallback = {} if default is None else default
    if not path.exists():
        return fallback
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    if default is None and not isinstance(payload, dict):
        return {}
    return payload


def read_required_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(redact_value(payload), indent=2, default=str),
        encoding="utf-8",
        newline="\n",
    )


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
