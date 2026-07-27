"""Shared writers for AutomationApplication run evidence export.

CLI and ops should use these helpers rather than inventing parallel export paths.
Payloads go through RunSummary.to_dict() so secret redaction stays centralized.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.automation.models import RunSummary


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
