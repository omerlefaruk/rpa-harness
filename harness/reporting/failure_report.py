"""
Failure report generation — produces structured failure_report.json + evidence.
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.core.artifacts import append_jsonl, write_json
from harness.core.time import utc_now_iso
from harness.resilience.errors import RULEBOOK_FAILURE_CLASSES, legacy_category_to_error_class
from harness.security import redact_value


FAILURE_KINDS = {
    "workflow_validation_error",
    "missing_secret",
    "selector_not_found",
    "ambiguous_selector",
    "action_failed",
    "verification_failed",
    "timeout",
    "input_data_error",
    "target_unavailable",
    "auth_failed",
    "permission_denied",
    "business_rule_rejected",
    "unexpected_state",
    "repair_candidate",
}


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
        *,
        current_stage: Optional[str] = None,
        intended_action: Optional[str] = None,
        expected_result: Optional[str] = None,
        actual_result: Optional[str] = None,
        input_record_id: Optional[str] = None,
        target_system: Optional[str] = None,
        retry_attempt: Optional[int] = None,
        max_attempts: Optional[int] = None,
        retry_allowed: Optional[bool] = None,
        side_effect_risk: Optional[str] = None,
        human_review_required: Optional[bool] = None,
        first_failed_stage: Optional[str] = None,
        last_known_good_stage: Optional[str] = None,
        escalation_status: Optional[str] = None,
        error_class: Optional[str] = None,
        failure_kind: Optional[str] = None,
    ) -> str:
        run_id = self._current_run_id or self.start_run(workflow_id)
        normalized_evidence = self._normalize_evidence(evidence or {})
        normalized_error_class = self._normalize_error_class(error_class, error_category)
        normalized_failure_kind = self._normalize_failure_kind(
            failure_kind=failure_kind,
            error_class=normalized_error_class,
            error_type=error_type,
            error_message=error_message,
            verification_failures=verification_failures or [],
        )

        report = {
            "schema_version": "1",
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "run_id": run_id,
            "status": "failed",
            "failure_kind": normalized_failure_kind,
            "current_stage": current_stage,
            "failed_step_id": failed_step_id,
            "failed_step_description": failed_step_description,
            "action_type": action_type,
            "intended_action": intended_action,
            "expected_result": expected_result,
            "actual_result": actual_result,
            "input_record_id": input_record_id,
            "target_system": target_system,
            "error_type": error_type,
            "error_message": error_message,
            "error_category": error_category,
            "error_class": normalized_error_class,
            "retry_attempt": retry_attempt,
            "max_attempts": max_attempts,
            "retry_allowed": retry_allowed,
            "side_effect_risk": side_effect_risk,
            "human_review_required": human_review_required,
            "first_failed_stage": first_failed_stage,
            "last_known_good_stage": last_known_good_stage,
            "escalation_status": escalation_status,
            "last_successful_step": last_successful_step or None,
            "verification_failures": verification_failures or [],
            "evidence": normalized_evidence,
            "suspected_causes": [],
            "recommended_patch": None,
            "repro_command": repro_command,
            "timestamp": utc_now_iso(),
            "duration_ms": duration_ms,
        }

        if self._run_dir:
            normalized_evidence["evidence_bundle"] = "evidence_bundle.json"
            normalized_evidence["repair_packet"] = "repair_packet.json"
            report["evidence"] = normalized_evidence
            repair_packet = self._repair_packet(report=report, evidence=normalized_evidence)
            write_json(self._run_dir / "repair_packet.json", repair_packet)
            bundle = self._evidence_bundle(
                report=report,
                failure_kind=normalized_failure_kind,
                evidence=normalized_evidence,
            )
            write_json(self._run_dir / "evidence_bundle.json", bundle)

        report_path = self._run_dir / "failure_report.json" if self._run_dir else None
        if report_path:
            write_json(report_path, report)

        return str(report_path) if report_path else ""

    def _normalize_error_class(self, error_class: Optional[str], error_category: str) -> str:
        if error_class:
            normalized = error_class.lower().replace("-", "_").replace(" ", "_")
            return normalized if normalized in RULEBOOK_FAILURE_CLASSES else "unknown"
        return legacy_category_to_error_class(error_category)

    def _normalize_failure_kind(
        self,
        *,
        failure_kind: Optional[str],
        error_class: str,
        error_type: str,
        error_message: str,
        verification_failures: List[Dict],
    ) -> str:
        if failure_kind:
            normalized = failure_kind.lower().replace("-", "_").replace(" ", "_")
            if normalized in FAILURE_KINDS:
                return normalized

        text = f"{error_type} {error_message}".lower()
        if "missing" in text and "secret" in text:
            return "missing_secret"
        if "validation" in text and "workflow" in text:
            return "workflow_validation_error"
        if "timeout" in text or "timed out" in text:
            return "timeout"
        if "permission" in text or "forbidden" in text:
            return "permission_denied"
        if "auth" in text or "login" in text or "unauthorized" in text:
            return "auth_failed"
        if "ambiguous" in text and "selector" in text:
            return "ambiguous_selector"
        if "selector" in text or "element not found" in text:
            return "selector_not_found"
        if verification_failures:
            return "verification_failed"
        if error_class == "data":
            return "input_data_error"
        if error_class == "business":
            return "business_rule_rejected"
        if error_class == "external_system":
            return "target_unavailable"
        if error_class == "automation_defect":
            return "repair_candidate"
        return "action_failed" if error_message else "unexpected_state"

    def _evidence_bundle(
        self,
        *,
        report: Dict[str, Any],
        failure_kind: str,
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        failed_check = None
        failures = report.get("verification_failures") or []
        if failures:
            failed_check = failures[0]
        desktop = evidence.get("desktop") if isinstance(evidence.get("desktop"), dict) else {}
        return {
            "schema_version": "1",
            "run_id": report.get("run_id"),
            "workflow_name": report.get("workflow_name"),
            "step_id": report.get("failed_step_id"),
            "failure_kind": failure_kind,
            "action_type": report.get("action_type"),
            "target_type": self._target_type(report.get("action_type")),
            "current_url": evidence.get("current_url"),
            "window_title": (evidence.get("desktop") or {}).get("window_title")
            if isinstance(evidence.get("desktop"), dict)
            else None,
            "input_record_id": report.get("input_record_id"),
            "artifacts": {
                "screenshot": evidence.get("screenshot") or evidence.get("desktop_screenshot"),
                "dom_snapshot": evidence.get("dom_snapshot"),
                "uia_snapshot": evidence.get("uia_tree"),
                "win32_snapshot": evidence.get("win32_tree"),
                "ocr_artifact": evidence.get("ocr_artifact"),
                "api_preview": evidence.get("api_response"),
                "logs": self._logs_path(),
                "selector_evidence": evidence.get("selector_repair"),
                "repair_packet": evidence.get("repair_packet"),
                "artifact_paths": evidence.get("artifact_paths") or [],
            },
            "desktop": desktop,
            "verification": {
                "checks_attempted": len(failures),
                "failed_check": failed_check,
            },
            "redaction": {
                "status": "redacted",
                "rules_version": "1",
            },
            "timestamps": {
                "created_at": report.get("timestamp"),
            },
        }

    def _repair_packet(
        self,
        *,
        report: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        failures = report.get("verification_failures") or []
        failed_check = failures[0] if failures else None
        return {
            "schema_version": "1",
            "workflow_name": report.get("workflow_name"),
            "run_id": report.get("run_id"),
            "step_id": report.get("failed_step_id"),
            "intended_action": report.get("intended_action") or report.get("failed_step_description"),
            "actual_failure": report.get("error_message"),
            "failure_kind": report.get("failure_kind"),
            "failed_verification": failed_check,
            "artifact_links": {
                key: value
                for key, value in evidence.items()
                if isinstance(value, str) and value
            },
            "selector_candidates": [],
            "safe_repair_scope": "Patch only the failed workflow step and rerun its success checks.",
            "protected_paths_reminder": (
                "Protected core harness, credentials, rules, and skills require "
                "reproduced failure, test, smallest patch, and verification."
            ),
            "recommended_next_action": self._recommended_next_action(report),
        }

    @staticmethod
    def _recommended_next_action(report: Dict[str, Any]) -> str:
        failure_kind = report.get("failure_kind")
        if failure_kind in {"selector_not_found", "ambiguous_selector", "repair_candidate"}:
            return "Run selector discovery, patch the failed selector, then rerun the workflow."
        if failure_kind == "missing_secret":
            return "Configure the missing secret environment variable and rerun."
        if failure_kind == "verification_failed":
            return "Inspect evidence, fix the success condition or target state, then rerun."
        return "Inspect the evidence bundle and rerun only after the cause is understood."

    @staticmethod
    def _target_type(action_type: Optional[str]) -> str:
        prefix = str(action_type or "").split(".", 1)[0]
        return prefix if prefix in {"browser", "desktop", "api", "excel", "workflow"} else "unknown"

    def _logs_path(self) -> Optional[str]:
        if self._run_dir and (self._run_dir / "logs.jsonl").exists():
            return "logs.jsonl"
        return None

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
            "timestamp": utc_now_iso(),
            "level": level,
            "step": step,
            "message": message,
        }
        if extra:
            entry.update(extra)
        append_jsonl(log_path, entry)
