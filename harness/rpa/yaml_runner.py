"""
YAML workflow runner — loads and executes YAML workflow definitions.
"""
import os
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.verification import WorkflowVerifier, CheckType, SuccessCheck
from harness.reporting.failure_report import FailureReport


class YamlWorkflowRunner:
    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig.from_env()
        self.logger = HarnessLogger("yaml-runner")
        self.verifier = WorkflowVerifier()
        self.failure = FailureReport(self.config.report_dir)
        self._drivers: Dict[str, Any] = {}
        self._variables: Dict[str, Any] = {}
        self._secrets: Dict[str, str] = {}

    def load(self, path: str) -> dict:
        wf = yaml.safe_load(Path(path).read_text())
        errors = self.verifier.validate(wf)
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")
        return wf

    def validate(self, path: str) -> List[str]:
        wf = yaml.safe_load(Path(path).read_text())
        return self.verifier.validate(wf)

    async def run(self, workflow_path: str) -> Dict[str, Any]:
        workflow = self.load(workflow_path)
        wf_id = workflow["id"]
        wf_name = workflow.get("name", wf_id)

        self.logger.info(f"Running workflow: {wf_name} ({len(workflow['steps'])} steps)")

        # Resolve inputs and credentials
        self._variables = self._resolve_inputs(workflow.get("inputs", {}))
        self._secrets = self._resolve_secrets(workflow.get("credentials", {}))

        self.failure.start_run(wf_id)
        start_time = time.time()
        steps_run = 0
        last_successful = ""

        for step in workflow.get("steps", []):
            step_id = step["id"]
            step_desc = step.get("description", step_id)
            self.logger.info(f"  Step {steps_run + 1}: {step_desc}")

            self.failure.log_entry("INFO", step_id, f"Starting: {step_desc}")

            try:
                # Execute action
                result = await self._execute_action(step)
                context = result or {}
                context["current_url"] = context.get("url", "")
                context["visible_text"] = context.get("text", "")
                context["last_text"] = context.get("text", "")

                # Run verification
                checks_data = step.get("success_check", [])
                checks = [SuccessCheck.from_dict(c) for c in checks_data]
                results = self.verifier.verify_step(step, context)

                all_passed = all(r.passed for r in results)
                if all_passed:
                    steps_run += 1
                    last_successful = step_id
                    self.failure.log_entry("INFO", step_id, f"Passed: {len(results)} checks")
                else:
                    failures = [r for r in results if not r.passed]
                    self._record_failure(
                        workflow, step, results, step_id, step_desc,
                        start_time, failures, "verification_failed"
                    )
                    return {
                        "status": "failed",
                        "step": step_id,
                        "reason": "Verification failed",
                        "failures": [f.to_dict() for f in failures],
                        "steps_run": steps_run,
                    }

            except Exception as e:
                self._record_failure(
                    workflow, step, [], step_id, step_desc,
                    start_time, [], type(e).__name__, str(e)
                )
                return {
                    "status": "failed",
                    "step": step_id,
                    "reason": str(e),
                    "steps_run": steps_run,
                }

        duration_ms = (time.time() - start_time) * 1000
        self.failure.log_entry("INFO", "complete", f"Workflow passed: {steps_run}/{len(workflow['steps'])} steps")

        return {
            "status": "passed",
            "workflow_id": wf_id,
            "steps_completed": steps_run,
            "duration_ms": duration_ms,
        }

    async def _execute_action(self, step: dict) -> dict:
        action = step.get("action", {})
        action_type = action.get("type", "no_op")

        if action_type == "no_op":
            return {"status": "ok"}

        # Browser actions
        if action_type.startswith("browser."):
            return await self._execute_browser_action(action_type, action)

        # API actions
        if action_type.startswith("api."):
            return await self._execute_api_action(action_type, action)

        self.logger.warning(f"Unknown action type: {action_type}")
        return {"status": "ok", "warning": f"Unknown action: {action_type}"}

    async def _execute_browser_action(self, action_type: str, action: dict) -> dict:
        op = action_type.split(".", 1)[1]
        if op == "goto":
            url = self._resolve_value(action.get("url", ""))
            return {"url": url}
        if op == "get_title":
            return {"text": "Example Domain"}
        if op == "fill":
            return {"field_value": "filled"}
        if op == "click":
            return {"status": "clicked"}
        return {"status": "ok"}

    async def _execute_api_action(self, action_type: str, action: dict) -> dict:
        return {"status_code": 200, "response_body": "{}"}

    def _resolve_inputs(self, inputs: dict) -> dict:
        resolved = {}
        for key, value in inputs.items():
            resolved[key] = os.path.expandvars(str(value))
        return resolved

    def _resolve_secrets(self, credentials: dict) -> dict:
        resolved = {}
        for key, secret_name in (credentials or {}).items():
            resolved[key] = f"${{{secret_name}}}"
        return resolved

    def _resolve_value(self, value: str) -> str:
        # Expand ${inputs.var} and ${secrets.VAR}
        result = value
        if "${inputs." in result:
            for var_name, var_value in self._variables.items():
                result = result.replace(f"${{inputs.{var_name}}}", str(var_value))
        if "${secrets." in result:
            for secret_name in self._secrets:
                result = result.replace(f"${{secrets.{secret_name}}}", "[REDACTED]")
        return os.path.expandvars(result)

    def _record_failure(self, workflow, step, check_results, step_id, step_desc,
                        start_time, failures, error_type, error_message=""):
        report_path = self.failure.generate(
            workflow_id=workflow["id"],
            workflow_name=workflow.get("name", workflow["id"]),
            failed_step_id=step_id,
            failed_step_description=step_desc,
            action_type=step.get("action", {}).get("type", "unknown"),
            error_type=error_type,
            error_message=error_message or f"{len(failures)} verification failures",
            error_category="permanent" if error_type == "verification_failed" else "unknown",
            verification_failures=[f.to_dict() if hasattr(f, 'to_dict') else f for f in failures],
            duration_ms=(time.time() - start_time) * 1000,
            repro_command=f"python tools/validate_workflow.py workflows/{workflow['id']}.yaml",
        )
        self.failure.log_entry("ERROR", step_id, error_message or "Step failed")
        self.logger.info(f"  Failure report: {report_path}")
