"""
Failure report generation — produces structured failure_report.json + evidence.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.security import redact_value


class FailureReport:
    def __init__(self, runs_dir: str = "./runs"):
        self.runs_dir = Path(runs_dir)
        self._current_run_id: Optional[str] = None
        self._run_dir: Optional[Path] = None

    def start_run(self, workflow_id: str) -> str:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        self._current_run_id = f"{ts}_{workflow_id}"
        self._run_dir = self.runs_dir / self._current_run_id
        for sub in ["screenshots", "dom", "artifacts"]:
            (self._run_dir / sub).mkdir(parents=True, exist_ok=True)
        return self._current_run_id

    def save_screenshot(self, data: bytes = None, path: str = None) -> str:
        if path and Path(path).exists():
            return str(path)
        if data and self._run_dir:
            dest = self._run_dir / "screenshots" / f"failure_{int(time.time()*1000)}.png"
            dest.write_bytes(data)
            return str(dest)
        return ""

    def save_dom(self, html: str) -> str:
        if self._run_dir and html:
            dest = self._run_dir / "dom" / f"snapshot_{int(time.time()*1000)}.html"
            dest.write_text(html)
            return str(dest)
        return ""

    def save_artifact(self, name: str, content: str) -> str:
        if self._run_dir:
            dest = self._run_dir / "artifacts" / name
            dest.write_text(content)
            return str(dest)
        return ""

    def generate(
        self,
        workflow_id: str,
        workflow_name: str,
        failed_step_id: str,
        failed_step_description: str,
        action_type: str,
        error_type: str,
        error_message: str,
        error_category: str = "unknown",
        last_successful_step: str = "",
        verification_failures: List[Dict] = None,
        evidence: Dict[str, Any] = None,
        duration_ms: float = 0,
        repro_command: str = "",
    ) -> str:
        run_id = self._current_run_id or self.start_run(workflow_id)
        normalized_evidence = self._normalize_evidence(evidence or {})

        report = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "run_id": run_id,
            "status": "failed",
            "failed_step_id": failed_step_id,
            "failed_step_description": failed_step_description,
            "action_type": action_type,
            "error_type": error_type,
            "error_message": error_message,
            "error_category": error_category,
            "last_successful_step": last_successful_step or None,
            "verification_failures": verification_failures or [],
            "evidence": normalized_evidence,
            "suspected_causes": [],
            "recommended_patch": None,
            "repro_command": repro_command,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
        }

        log_path = self._run_dir / "logs.jsonl" if self._run_dir else None

        report_path = self._run_dir / "failure_report.json" if self._run_dir else None
        if report_path:
            report_path.write_text(json.dumps(redact_value(report), indent=2, default=str))

        return str(report_path) if report_path else ""

    def _normalize_evidence(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(evidence)
        artifact_paths = list(normalized.get("artifact_paths") or [])
        for key in ("api_response", "console_logs", "network_logs"):
            value = normalized.get(key)
            if isinstance(value, str) and value and value not in artifact_paths:
                artifact_paths.append(value)
        if artifact_paths:
            normalized["artifact_paths"] = artifact_paths
        return normalized

    def log_entry(self, level: str, step: str, message: str, extra: dict = None):
        if not self._run_dir:
            return
        log_path = self._run_dir / "logs.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "step": step,
            "message": message,
        }
        if extra:
            entry.update(extra)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
