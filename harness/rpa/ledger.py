"""Append-only resume ledger for record-oriented RPA runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.core.artifacts import read_jsonl
from harness.core.time import utc_now_iso
from harness.security import redact_value


class ResumeLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_item(
        self,
        workflow: str,
        record_id: str,
        status: str,
        *,
        stage: str | None = None,
        idempotency_key: str | None = None,
        external_reference_id: str | None = None,
        evidence_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = redact_value(
            {
                "timestamp": utc_now_iso(),
                "workflow": workflow,
                "record_id": record_id,
                "status": status,
                "stage": stage,
                "idempotency_key": idempotency_key,
                "external_reference_id": external_reference_id,
                "evidence_path": evidence_path,
                "details": details or {},
            }
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
        return entry

    def latest_by_record(self, workflow: str | None = None) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for entry in read_jsonl(self.path):
            if workflow and entry.get("workflow") != workflow:
                continue
            record_id = str(entry.get("record_id") or "")
            if record_id:
                latest[record_id] = entry
        return latest

    def summary(self, workflow: str | None = None) -> dict[str, Any]:
        latest = self.latest_by_record(workflow=workflow)
        counts: dict[str, int] = {}
        for entry in latest.values():
            status = str(entry.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        return {
            "path": str(self.path),
            "records": len(latest),
            "status_counts": counts,
            "latest": latest,
        }
