"""Governed desktop AI assistance.

This module deliberately does not execute free-form AI output. It turns desktop
evidence into redacted inspection/repair packets and validates approved
deterministic YAML steps before normal workflow execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.core.artifacts import read_json
from harness.security import is_sensitive_key, redact_value
from harness.verification.contract import DESKTOP_ACTIONS, validate_workflow_step

DISCOVERY_PATTERNS = (
    "evidence_bundle.json",
    "selector_evidence.json",
    "artifacts/selector_evidence.json",
    "artifacts/selector_repair_suggestion.json",
    "artifacts/uia_tree.json",
    "artifacts/win32_tree.json",
    "artifacts/ocr_result*.json",
    "screenshots/*.png",
    "*.png",
)


class DesktopAIController:
    def __init__(self, session_dir: str | Path):
        self.session_dir = Path(session_dir)

    def run(self, mode: str = "inspect", proposal_path: str | Path | None = None) -> dict[str, Any]:
        mode = mode.replace("_", "-")
        if mode == "inspect":
            return self.inspect()
        if mode == "draft":
            return self.draft()
        if mode == "repair":
            return self.repair()
        if mode == "execute-approved":
            default_proposal = self.session_dir / "approved_desktop_proposal.json"
            proposal = read_json(Path(proposal_path) if proposal_path else default_proposal)
            decision = self.validate_proposal(
                proposal,
                require_approval=True,
                require_evidence=True,
            )
            decision["output"] = self._write_json("desktop_ai_execution_decision.json", decision)
            return decision
        return {"status": "blocked", "reason": f"Unsupported desktop AI mode: {mode}"}

    def inspect(self) -> dict[str, Any]:
        evidence = self.evidence_summary()
        status = "ready" if evidence["evidence_files"] else "needs_capture"
        result = {
            "schema_version": 1,
            "status": status,
            "session_dir": str(self.session_dir),
            "evidence": evidence,
            "next_actions": self._next_actions(evidence),
        }
        result["output"] = self._write_json("desktop_ai_inspection.json", result)
        return result

    def draft(self) -> dict[str, Any]:
        inspection = self.inspect()
        proposals = []
        if inspection["status"] == "ready":
            proposals.append(
                {
                    "id": "desktop_step_template",
                    "status": "needs_human_approval",
                    "side_effect": "none",
                    "step": {
                        "id": "replace_with_step_id",
                        "action": {
                            "type": "desktop.click",
                            "selector": {
                                "strategy": "automation_id",
                                "value": "replace_with_stable_automation_id",
                            },
                        },
                        "success_check": [{"type": "element_exists"}],
                    },
                    "approval_required": True,
                    "reason": (
                        "Template only; replace selector with a validated desktop evidence "
                        "candidate."
                    ),
                }
            )
        result = {
            "schema_version": 1,
            "status": "ready" if proposals else "blocked",
            "reason": None if proposals else "No desktop discovery evidence found.",
            "proposals": proposals,
            "inspection": inspection,
        }
        result["output"] = self._write_json("desktop_ai_proposals.json", result)
        return result

    def repair(self) -> dict[str, Any]:
        evidence = self.evidence_summary()
        status = "ready" if evidence["evidence_files"] else "blocked"
        result = {
            "schema_version": 1,
            "status": status,
            "reason": None if status == "ready" else "No desktop discovery evidence found.",
            "session_dir": str(self.session_dir),
            "selector_policy": [
                "automation_id",
                "name+control_type",
                "class_name+control_type",
                "tree_path",
                "image_anchor",
                "coordinate_fallback",
            ],
            "requirements": [
                "Patch only the failed workflow step.",
                "Use success_check for the intended outcome.",
                "Use logical secret names only; never paste literal secrets into artifacts.",
                "Coordinate fallback requires x_ratio/y_ratio plus explicit verification.",
            ],
            "evidence": evidence,
        }
        result["json_output"] = self._write_json("desktop_ai_repair_packet.json", result)
        result["markdown_output"] = self._write_text(
            "desktop_ai_repair_packet.md",
            self._repair_markdown(result),
        )
        return result

    def validate_proposal(
        self,
        proposal: dict[str, Any],
        *,
        require_approval: bool = False,
        require_evidence: bool = False,
    ) -> dict[str, Any]:
        issues: list[str] = []
        if not isinstance(proposal, dict) or not proposal:
            return {
                "status": "blocked",
                "reason": "Approved proposal JSON is missing or invalid.",
                "issues": [],
            }
        if require_approval and proposal.get("approved") is not True:
            issues.append("proposal must include approved: true")
        if require_evidence and not self.evidence_summary()["evidence_files"]:
            issues.append("desktop discovery evidence is required before approved execution")

        step = self._proposal_step(proposal)
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        action_type = str(action.get("type") or "")
        if action_type not in DESKTOP_ACTIONS:
            issues.append(f"unsupported desktop action: {action_type or 'missing'}")

        checks = step.get("success_check") or []
        if isinstance(checks, dict):
            checks = [checks]
            step = {**step, "success_check": checks}
        if not checks:
            issues.append("desktop proposal step must include success_check")
        else:
            issues.extend(validate_workflow_step(step))

        side_effect = str(proposal.get("side_effect") or step.get("side_effect") or "").strip()
        if not side_effect:
            issues.append("proposal must declare side_effect")
        if (
            side_effect in {"external_write", "destructive"}
            and proposal.get("approved_external_write") is not True
        ):
            issues.append(
                "external_write/destructive desktop proposal requires "
                "approved_external_write: true"
            )
        if side_effect in {"external_write", "destructive"} and self._has_retry(step):
            issues.append("non-idempotent external writes must not be retried automatically")

        issues.extend(self._selector_governance_issues(action, step, proposal))
        issues.extend(self._literal_secret_issues(action))

        status = "approved" if not issues else "blocked"
        result = {
            "schema_version": 1,
            "status": status,
            "issues": issues,
            "proposal": redact_value(proposal),
        }
        if status == "approved":
            result["execution_packet"] = {
                "mode": "deterministic_yaml_step",
                "step": redact_value(step),
                "next_action": (
                    "Insert this step into a workflow and run it with main.py --run-yaml."
                ),
            }
        return result

    def evidence_summary(self) -> dict[str, Any]:
        files = []
        for path in self._evidence_files():
            entry: dict[str, Any] = {
                "path": str(path.relative_to(self.session_dir)),
                "size": path.stat().st_size,
            }
            if path.suffix.lower() in {".json", ".jsonl", ".md", ".txt"}:
                entry["preview"] = self._preview(path)
            files.append(entry)
        return {
            "session_exists": self.session_dir.exists(),
            "evidence_files": files,
        }

    def _evidence_files(self) -> list[Path]:
        if not self.session_dir.exists():
            return []
        found: list[Path] = []
        for pattern in DISCOVERY_PATTERNS:
            found.extend(path for path in self.session_dir.glob(pattern) if path.is_file())
        return sorted(set(found))

    def _preview(self, path: Path, max_chars: int = 1000) -> Any:
        text = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        if path.suffix.lower() == ".json":
            try:
                return redact_value(json.loads(text))
            except json.JSONDecodeError:
                return redact_value(text)
        return redact_value(text)

    def _write_json(self, name: str, payload: dict[str, Any]) -> str:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        path = self.session_dir / name
        path.write_text(json.dumps(redact_value(payload), indent=2, default=str), encoding="utf-8")
        return str(path)

    def _write_text(self, name: str, text: str) -> str:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        path = self.session_dir / name
        path.write_text(str(redact_value(text)), encoding="utf-8")
        return str(path)

    @staticmethod
    def _proposal_step(proposal: dict[str, Any]) -> dict[str, Any]:
        step = proposal.get("step") if isinstance(proposal.get("step"), dict) else proposal
        return dict(step) if isinstance(step, dict) else {}

    @staticmethod
    def _has_retry(step: dict[str, Any]) -> bool:
        for recovery in step.get("recovery", []) or []:
            if isinstance(recovery, dict) and recovery.get("type") == "retry":
                return True
        return False

    def _selector_governance_issues(
        self,
        action: dict[str, Any],
        step: dict[str, Any],
        proposal: dict[str, Any],
    ) -> list[str]:
        selector = action.get("selector") if isinstance(action.get("selector"), dict) else {}
        strategy = str(selector.get("strategy") or "").lower()
        issues: list[str] = []
        if strategy == "coordinate":
            value = selector.get("value") if isinstance(selector.get("value"), dict) else {}
            if "x" in value or "y" in value:
                issues.append("coordinate fallback must use x_ratio/y_ratio, not absolute x/y")
            if "x_ratio" not in value or "y_ratio" not in value:
                issues.append("coordinate fallback requires x_ratio and y_ratio")
            if action.get("allow_coordinate_fallback") is not True:
                issues.append("coordinate fallback requires allow_coordinate_fallback: true")
        if strategy in {"coordinate", "tree_path", "image", "ocr"}:
            weak_reason = (
                proposal.get("weak_step_reason")
                or step.get("weak_step_reason")
                or action.get("weak_step_reason")
            )
            verification = proposal.get("verification_method") or step.get("verification_method")
            if not weak_reason:
                issues.append("weak desktop selectors require weak_step_reason")
            if not verification:
                issues.append("weak desktop selectors require verification_method")
        return issues

    @staticmethod
    def _literal_secret_issues(action: dict[str, Any]) -> list[str]:
        issues = []
        action_type = str(action.get("type") or "")
        for path, key, value in _walk(action):
            if action_type == "desktop.clipboard_paste" and key == "secret":
                continue
            if is_sensitive_key(key) and isinstance(value, str) and "${secrets." not in value:
                issues.append(f"literal secret value is not allowed at action.{path}")
        return issues

    @staticmethod
    def _next_actions(evidence: dict[str, Any]) -> list[str]:
        if not evidence["evidence_files"]:
            return [
                "Capture UIA/Win32 tree, screenshot, and selector evidence before "
                "drafting actions."
            ]
        return [
            "Draft a deterministic desktop YAML step from stable selector evidence.",
            "Require human approval before any action is handed to the YAML runner.",
        ]

    @staticmethod
    def _repair_markdown(result: dict[str, Any]) -> str:
        files = (
            "\n".join(f"- {item['path']}" for item in result["evidence"]["evidence_files"])
            or "- none"
        )
        requirements = "\n".join(f"- {item}" for item in result["requirements"])
        return (
            "# Desktop AI Repair Packet\n\n"
            f"Status: {result['status']}\n\n"
            "## Evidence\n"
            f"{files}\n\n"
            "## Requirements\n"
            f"{requirements}\n"
        )


def _walk(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{prefix}[{index}]"
            yield child_path, str(index), child
            yield from _walk(child, child_path)
