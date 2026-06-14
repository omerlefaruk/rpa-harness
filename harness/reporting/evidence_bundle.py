"""Create portable sanitized evidence bundles for failed runs."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from harness.security import redact_value


def bundle_run(run_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(run_path).resolve()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Run directory not found: {source}")
    destination = Path(output_path).resolve() if output_path else source.with_suffix(".zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        manifest = _manifest(source)
        bundle.writestr("bundle_manifest.json", json.dumps(manifest, indent=2, default=str))
        for path in sorted(source.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(source).as_posix())
    return destination


def _manifest(source: Path) -> dict[str, Any]:
    report_path = source / "failure_report.json"
    report = {}
    if report_path.exists():
        report = redact_value(json.loads(report_path.read_text(encoding="utf-8")))
    return {
        "run_dir": source.name,
        "failure_report": report,
        "files": [
            {
                "path": path.relative_to(source).as_posix(),
                "size": path.stat().st_size,
            }
            for path in sorted(source.rglob("*"))
            if path.is_file()
        ],
    }
