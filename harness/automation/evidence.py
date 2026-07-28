"""Shared writers for AutomationApplication run evidence export.

CLI and ops should use these helpers rather than inventing parallel export paths.
Payloads go through RunSummary.to_dict() so secret redaction stays centralized.
"""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from harness.automation.models import RunSummary
from harness.security import redact_value


class EvidenceStore:
    """Content-addressed, redacted artifact storage used by lifecycle sinks."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def put(self, value: Any) -> tuple[str, int, Path]:
        payload = json.dumps(redact_value(value), sort_keys=True, separators=(",", ":"), default=str).encode()
        digest = hashlib.sha256(payload).hexdigest()
        path = self.root / "artifacts" / "sha256" / digest[:2] / f"{digest}.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=f"{digest}.", dir=str(path.parent))
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(payload)
                Path(tmp_name).replace(path)
            finally:
                Path(tmp_name).unlink(missing_ok=True)
        return digest, len(payload), path

    def read(self, content_hash: str) -> Any:
        path = self.root / "artifacts" / "sha256" / content_hash[:2] / f"{content_hash}.json"
        return json.loads(path.read_text(encoding="utf-8"))


def run_evidence_payload(summary: RunSummary) -> dict[str, Any]:
    """Redacted run summary suitable for reports, logs, and evidence bundles."""

    return summary.to_dict()


def export_run_evidence(summary: RunSummary, directory: Path | str) -> Path:
    """Write redacted run evidence JSON under *directory*; return the file path."""

    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{summary.run_id}_evidence.json"
    path.write_text(
        json.dumps(run_evidence_payload(summary), indent=2, default=str),
        encoding="utf-8",
    )
    return path
