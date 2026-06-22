"""
YAML workflow runner.

Loads validated YAML workflows and executes the supported v1 action set against
real browser/API drivers.
"""

import json
import os
import re
import time
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from harness.config import HarnessConfig
from harness.core import audit_workflow_rulebook
from harness.core.artifacts import read_json, read_jsonl
from harness.core.ids import INPUT_REF_RE
from harness.copilot import CopilotCheckpoint
from harness.logger import HarnessLogger
from harness.notifications import BotNotifier
from harness.reporting.failure_report import FailureReport
from harness.resilience.errors import classify_failure
from harness.rpa.execution_plan import build_execution_plan
from harness.selectors.repair import selector_repair_plan
from harness.security import (
    SecretValue,
    SECRET_REF_RE,
    redact_mapping,
    redact_text,
    redact_value,
    redacted_preview,
    sanitize_url,
)
from harness.verification import (
    CheckType,
    SuccessCheck,
    VerificationResult,
    WorkflowVerifier,
    preflight_workflow,
)
from harness.verification.checks import CheckRunner

VARIABLE_REF_RE = re.compile(r"\$\{variables\.([A-Za-z_][A-Za-z0-9_]*)\}")
FILE_PWD_REF_RE = re.compile(r"file://\$PWD(?![A-Za-z0-9_])")
PWD_REF_RE = re.compile(r"(?<![A-Za-z0-9_])\$PWD(?![A-Za-z0-9_])")

SUPPORTED_RUNTIME_PREFIXES = ("browser.", "api.", "desktop.", "excel.")


def load_workflow_yaml(path: str | Path) -> dict:
    from harness.rpa.schema import load_workflow_yaml_compat

    return load_workflow_yaml_compat(path)


class YamlWorkflowRunner:
    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig.from_env()
        self.logger = HarnessLogger("yaml-runner")
        self.verifier = WorkflowVerifier()
        self.failure = FailureReport("./runs")
        self.notifier = BotNotifier.from_env(source="yaml-runner")
        self._drivers: Dict[str, Any] = {}
        self._inputs: Dict[str, Any] = {}
        self._variables: Dict[str, Any] = {}
        self._secret_env_names: Dict[str, str] = {}
        self._secrets: Dict[str, SecretValue] = {}
        self._workflow_path = ""
        self._last_api_context: Optional[Dict[str, Any]] = None
        self._console_entries: List[dict] = []
        self._network_entries: List[dict] = []
        self._pending_logs: List[dict] = []
        self._copilot: Any = None

    def load(self, path: str) -> dict:
        workflow = load_workflow_yaml(path)
        errors = self.verifier.validate(workflow)
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")
        return workflow

    def validate(self, path: str) -> List[str]:
        workflow = load_workflow_yaml(path)
        return self.verifier.validate(workflow)

    async def preflight(self, workflow_path: str) -> Dict[str, Any]:
        self._workflow_path = str(workflow_path)
        workflow = self.load(workflow_path)
        workflow_id = workflow["id"]
        workflow_name = workflow.get("name", workflow_id)
        self.failure.start_run(workflow_id)
        started_at = self._now()
        self._inputs = self._resolve_inputs(workflow.get("inputs", {}))
        self._secret_env_names = self._resolve_secret_env_names(workflow.get("credentials", {}))

        self._write_manifest(workflow, "running", started_at=started_at)
        self._write_redacted_workflow(workflow)
        self._timeline(workflow, "run.started", status="running")
        self._timeline(workflow, "preflight.started")
        preflight = preflight_workflow(workflow, inputs=self._inputs)
        self._write_preflight(preflight, workflow, started_at)
        status = "passed" if preflight["status"] == "passed" else "failed"
        self._timeline(workflow, f"preflight.{status}", status=status)
        self._timeline(workflow, "run.finished", status=status)
        result = {
            "status": status,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "preflight": preflight,
            "run_id": self.failure._current_run_id,
            "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
        }
        self._write_manifest(workflow, status, started_at=started_at, finished_at=self._now(), result=result)
        self._write_run_report(workflow, result)
        return result

    async def run(
        self,
        workflow_path: str,
        *,
        phase: Optional[str] = None,
        pause_before: Optional[str] = None,
        pause_after_phase: Optional[str] = None,
        until_step: Optional[str] = None,
        only_record: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._workflow_path = str(workflow_path)
        workflow = self.load(workflow_path)
        workflow_id = workflow["id"]
        workflow_name = workflow.get("name", workflow_id)
        rulebook_audit = audit_workflow_rulebook(workflow).to_dict()
        self._last_api_context = None
        self._console_entries = []
        self._network_entries = []
        self._pending_logs = []
        self.failure.start_run(workflow_id)
        run_started_at = self._now()
        self._write_manifest(workflow, "running", started_at=run_started_at)
        self._write_redacted_workflow(workflow)
        self._timeline(workflow, "run.started", status="running")

        self._inputs = self._resolve_inputs(workflow.get("inputs", {}))
        self._variables = dict(self._inputs)
        self._secret_env_names = self._resolve_secret_env_names(workflow.get("credentials", {}))

        missing_secrets = self._missing_secrets()
        if missing_secrets:
            self._write_preflight(
                {
                    "status": "failed",
                    "passed_checks": [],
                    "warnings": [],
                    "blocking_errors": [
                        f"preflight: missing secret '{item['name']}' ({item['env']})"
                        for item in missing_secrets
                    ],
                },
                workflow,
                run_started_at,
            )
            self._timeline(workflow, "preflight.failed", status="failed", failure_kind="missing_secret")
            result = {
                "status": "failed",
                "state": "needs_operator_input",
                "failure_type": "config",
                "reason": "Missing required secrets",
                "missing_secrets": missing_secrets,
                "steps": [],
                "rulebook_audit": rulebook_audit,
                "run_id": self.failure._current_run_id,
                "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
            }
            self._timeline(workflow, "run.finished", status="failed", failure_kind="missing_secret")
            self._write_manifest(workflow, "failed", started_at=run_started_at, finished_at=self._now(), result=result)
            self._write_run_report(workflow, result)
            await self.notifier.question(
                "I cannot start this YAML workflow because required secrets are missing.",
                context={
                    "workflow": workflow_name,
                    "missing": ", ".join(item["name"] for item in missing_secrets),
                },
            )
            return result
        self._secrets = self._load_secrets()
        self.notifier.add_secret_values(self._secret_values())

        self._timeline(workflow, "preflight.started")
        preflight = preflight_workflow(workflow, inputs=self._inputs)
        self._write_preflight(preflight, workflow, run_started_at)
        if preflight["blocking_errors"]:
            self._timeline(workflow, "preflight.failed", status="failed", failure_kind="workflow_validation_error")
            result = {
                "status": "failed",
                "failure_type": "preflight",
                "reason": "Preflight checks failed",
                "preflight": preflight,
                "steps": [],
                "rulebook_audit": rulebook_audit,
                "run_id": self.failure._current_run_id,
                "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
            }
            self._timeline(workflow, "run.finished", status="failed", failure_kind="workflow_validation_error")
            self._write_manifest(workflow, "failed", started_at=run_started_at, finished_at=self._now(), result=result)
            self._write_run_report(workflow, result)
            return result
        self._timeline(workflow, "preflight.passed", status="passed")

        selection_error = self._selection_error(
            workflow,
            phase,
            pause_before,
            pause_after_phase,
            until_step,
            only_record,
            inputs=self._variables,
        )
        if selection_error:
            result = {
                "status": "failed",
                "failure_type": "selection",
                "reason": selection_error,
                "steps": [],
                "rulebook_audit": rulebook_audit,
                "run_id": self.failure._current_run_id,
                "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
            }
            self._timeline(workflow, "run.finished", status="failed", failure_kind="workflow_validation_error", message=selection_error)
            self._write_manifest(workflow, "failed", started_at=run_started_at, finished_at=self._now(), result=result)
            self._write_run_report(workflow, result)
            return result

        unsupported = self._unsupported_runtime_actions(workflow)
        if unsupported:
            result = {
                "status": "failed",
                "failure_type": "unsupported",
                "reason": "Workflow contains actions not supported by YAML execution v1",
                "unsupported_actions": unsupported,
                "steps": [],
                "rulebook_audit": rulebook_audit,
                "run_id": self.failure._current_run_id,
                "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
            }
            self._timeline(workflow, "run.finished", status="failed", failure_kind="workflow_validation_error")
            self._write_manifest(workflow, "failed", started_at=run_started_at, finished_at=self._now(), result=result)
            self._write_run_report(workflow, result)
            await self.notifier.question(
                "This YAML workflow has actions I do not know how to run yet.",
                context={
                    "workflow": workflow_name,
                    "actions": ", ".join(unsupported),
                },
            )
            return result

        start_time = time.time()
        steps: List[Dict[str, Any]] = []
        last_successful_step = ""
        original_auto_heal = self.config.auto_heal_selectors
        self.config.auto_heal_selectors = False

        execution_plan = build_execution_plan(
            workflow,
            inputs=self._variables,
            phase=phase,
            only_record=only_record,
        )
        selected_steps = execution_plan.steps
        self.logger.info(f"Running workflow: {workflow_name} ({len(selected_steps)} steps)")

        try:
            active_phase = None
            for step in selected_steps:
                step_phase = self._step_phase(step)
                if step_phase != active_phase:
                    if active_phase:
                        self._timeline(workflow, "phase.passed", status="passed", phase=active_phase)
                    active_phase = step_phase
                    self._timeline(workflow, "phase.started", status="running", phase=step_phase)

                if pause_before == step["id"] or step.get("pause_before") is True:
                    should_pause = True
                    if self._copilot_enabled():
                        decision = await self._ask_copilot(
                            workflow,
                            step,
                            step_phase,
                            reason="pause_before",
                        )
                        if decision.get("action") == "continue":
                            should_pause = False
                    if should_pause:
                        result = self._paused_result(
                            workflow, step, steps, rulebook_audit, run_started_at, "pause_before"
                        )
                        self._timeline(workflow, "run.paused", status="blocked", phase=step_phase, step_id=step["id"])
                        self._write_manifest(workflow, "blocked", started_at=run_started_at, finished_at=self._now(), result=result)
                        self._write_run_report(workflow, result)
                        return result

                self._record_step(workflow, step, "running")
                self._timeline(workflow, "step.started", status="running", phase=step_phase, step_id=step["id"], action_type=step.get("action", {}).get("type"))
                step_result = await self._run_step(step)
                steps.append(step_result)

                if step_result["status"] == "passed":
                    self._record_step(workflow, step, "passed", step_result=step_result)
                    self._timeline(workflow, "step.passed", status="passed", phase=step_phase, step_id=step["id"], action_type=step_result.get("action_type"), duration_ms=step_result.get("duration_ms"))
                    last_successful_step = step["id"]
                    if until_step == step["id"]:
                        result = {
                            "status": "passed",
                            "workflow_id": workflow_id,
                            "workflow_name": workflow_name,
                            "steps_completed": len(steps),
                            "steps": steps,
                            "duration_ms": (time.time() - start_time) * 1000,
                            "rulebook_audit": rulebook_audit,
                            "run_id": self.failure._current_run_id,
                            "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
                        }
                        self._timeline(workflow, "run.finished", status="passed", message=f"Stopped at --until-step {until_step}")
                        self._write_manifest(workflow, "passed", started_at=run_started_at, finished_at=self._now(), result=result)
                        self._write_run_report(workflow, result)
                        return result
                    if pause_after_phase and pause_after_phase == step_phase:
                        remaining = [
                            item for item in selected_steps[selected_steps.index(step) + 1 :]
                            if self._step_phase(item) == step_phase
                        ]
                        if not remaining:
                            if self._copilot_enabled():
                                decision = await self._ask_copilot(
                                    workflow,
                                    step,
                                    step_phase,
                                    reason="pause_after_phase",
                                )
                                if decision.get("action") == "continue":
                                    continue
                            result = self._paused_result(
                                workflow, step, steps, rulebook_audit, run_started_at, "pause_after_phase"
                            )
                            self._timeline(workflow, "run.paused", status="blocked", phase=step_phase, step_id=step["id"])
                            self._write_manifest(workflow, "blocked", started_at=run_started_at, finished_at=self._now(), result=result)
                            self._write_run_report(workflow, result)
                            return result
                    continue

                report_path = await self._record_failure(
                    workflow=workflow,
                    step=step,
                    step_result=step_result,
                    started_at=start_time,
                    last_successful_step=last_successful_step,
                )
                step_result["failure_report"] = report_path
                evidence_bundle = "evidence_bundle.json" if report_path else None
                self._record_step(
                    workflow,
                    step,
                    "failed",
                    step_result=step_result,
                    evidence_bundle=evidence_bundle,
                )
                self._timeline(
                    workflow,
                    "step.failed",
                    status="failed",
                    phase=step_phase,
                    step_id=step["id"],
                    action_type=step_result.get("action_type"),
                    failure_kind=step_result.get("failure_kind"),
                    evidence_bundle=evidence_bundle,
                    duration_ms=step_result.get("duration_ms"),
                )
                self._timeline(workflow, "phase.failed", status="failed", phase=step_phase, failure_kind=step_result.get("failure_kind"))
                self._timeline(workflow, "evidence.created", phase=step_phase, step_id=step["id"], evidence_bundle=evidence_bundle)
                self._timeline(workflow, "repair_packet.created", phase=step_phase, step_id=step["id"], evidence_bundle="repair_packet.json")
                await self.notifier.failure(
                    "A YAML workflow step failed.",
                    context={
                        "workflow": workflow_name,
                        "step": step["id"],
                        "reason": step_result.get("error") or "Verification failed",
                        "failure_report": report_path,
                    },
                )
                if step_result.get("attempts", 0) > 1:
                    await self.notifier.frustration(
                        "I retried this YAML step and it still failed.",
                        context={
                            "workflow": workflow_name,
                            "step": step["id"],
                            "attempts": step_result.get("attempts"),
                        },
                    )
                result = {
                    "status": "failed",
                    "failure_type": "execution",
                    "workflow_id": workflow_id,
                    "workflow_name": workflow_name,
                    "step": step["id"],
                    "reason": step_result.get("error") or "Verification failed",
                    "failure_report": report_path,
                    "steps": steps,
                    "duration_ms": (time.time() - start_time) * 1000,
                    "rulebook_audit": rulebook_audit,
                    "run_id": self.failure._current_run_id,
                    "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
                }
                self._timeline(workflow, "run.finished", status="failed", failure_kind=step_result.get("failure_kind"))
                self._write_manifest(workflow, "failed", started_at=run_started_at, finished_at=self._now(), result=result)
                self._write_run_report(workflow, result)
                return result

            if active_phase:
                self._timeline(workflow, "phase.passed", status="passed", phase=active_phase)
            result = {
                "status": "passed",
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "steps_completed": len(steps),
                "steps": steps,
                "duration_ms": (time.time() - start_time) * 1000,
                "rulebook_audit": rulebook_audit,
                "run_id": self.failure._current_run_id,
                "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
            }
            self._timeline(workflow, "run.finished", status="passed")
            self._write_manifest(workflow, "passed", started_at=run_started_at, finished_at=self._now(), result=result)
            self._write_run_report(workflow, result)
            return result
        finally:
            self.config.auto_heal_selectors = original_auto_heal
            await self._close_drivers()

    async def _run_step(self, step: dict) -> Dict[str, Any]:
        step_id = step["id"]
        step_desc = step.get("description", step_id)
        action_type = step.get("action", {}).get("type", "no_op")
        destructive = action_type in {"api.post", "api.put", "api.patch", "api.delete"}
        started_at = time.time()
        attempts = 0
        check_results: List[VerificationResult] = []
        action_result: Dict[str, Any] = {}
        last_error = ""

        self._log_entry("INFO", step_id, f"Starting: {step_desc}")

        async def try_action_and_verify() -> bool:
            nonlocal attempts
            nonlocal action_result
            nonlocal check_results
            nonlocal last_error
            attempts += 1
            try:
                action_result = await self._execute_action(step)
                check_results = await self._verify_step(step, action_result)
                last_error = ""
            except Exception as exc:
                last_error = str(exc)
                check_results = []
            return self._checks_passed(check_results)

        def passed_step_result() -> Dict[str, Any]:
            return self._step_result(
                step, step_id, action_type, started_at, attempts, check_results, destructive
            )

        if await try_action_and_verify():
            return passed_step_result()

        for recovery in step.get("recovery", []) or []:
            recovery_type = recovery.get("type")

            if recovery_type == "retry":
                max_attempts = int(recovery.get("max_attempts", 1))
                while attempts < max_attempts:
                    if attempts > 0:
                        await self.notifier.frustration(
                            "I am retrying a YAML step because the check did not pass.",
                            context={"step": step_id, "attempt": attempts + 1},
                        )
                    if await try_action_and_verify():
                        return passed_step_result()

            elif recovery_type == "wait":
                await self.notifier.frustration(
                    "I am waiting before checking this YAML step again.",
                    context={
                        "step": step_id,
                        "wait_ms": recovery.get("ms", recovery.get("duration_ms", 1000)),
                    },
                )
                await self._sleep_ms(int(recovery.get("ms", recovery.get("duration_ms", 1000))))
                should_reexecute = bool(last_error) or action_type.startswith("api.")
                if should_reexecute:
                    passed = await try_action_and_verify()
                else:
                    check_results = await self._verify_step(step, action_result)
                    passed = self._checks_passed(check_results)
                if passed:
                    return passed_step_result()

            elif recovery_type == "refresh_page":
                await self.notifier.frustration(
                    "I am refreshing the page to recover this YAML step.",
                    context={"step": step_id},
                )
                browser = self._drivers.get("browser")
                if browser and browser.page:
                    await browser.page.reload(wait_until="load")
                if await try_action_and_verify():
                    return passed_step_result()

        result = self._step_result(
            step, step_id, action_type, started_at, attempts, check_results, destructive
        )
        result["status"] = "failed"
        result["error"] = self._redact_runtime_text(
            last_error or self._verification_error(check_results)
        )
        result["failure_kind"] = self._failure_kind(result["error"], check_results)
        result["failure_route"] = classify_failure(result["error"]).get("recommended_route")
        self._log_entry("ERROR", step_id, result["error"])
        return result

    def _step_result(
        self,
        step: dict,
        step_id: str,
        action_type: str,
        started_at: float,
        attempts: int,
        check_results: List[VerificationResult],
        destructive: bool,
    ) -> Dict[str, Any]:
        result = {
            "step_id": step_id,
            "phase": self._step_phase(step),
            "action_type": action_type,
            "status": "passed" if self._checks_passed(check_results) else "failed",
            "duration_ms": (time.time() - started_at) * 1000,
            "attempts": attempts,
            "max_attempts": self._step_max_attempts(step),
            "current_stage": step.get("current_stage") or step_id,
            "intent": step.get("intent") or step.get("description", ""),
            "proof": step.get("proof") or "",
            "failure_path": step.get("failure_path") or "",
            "checks": [self._redact_check_result(result) for result in check_results],
            "destructive": destructive,
            "safe_retry": self._safe_retry(step, action_type),
            "error": "",
        }
        if step.get("record_id") is not None:
            result["record_id"] = str(step.get("record_id"))
        if step.get("row_number") is not None:
            result["row_number"] = step.get("row_number")
        return result

    async def _execute_action(self, step: dict) -> Dict[str, Any]:
        action = step.get("action", {})
        action_type = action.get("type", "no_op")

        if action_type == "no_op":
            return {"status": "ok"}
        if action_type.startswith("browser."):
            return await self._execute_browser_action(action_type, action)
        if action_type.startswith("api."):
            return await self._execute_api_action(action_type, action)
        if action_type.startswith("desktop."):
            return await self._execute_desktop_action(action_type, action)
        if action_type.startswith("excel."):
            return await self._execute_excel_action(action_type, action)

        raise RuntimeError(f"Execution is not supported for action type: {action_type}")

    async def _execute_browser_action(self, action_type: str, action: dict) -> Dict[str, Any]:
        driver = await self._get_browser_driver()
        page = driver.page
        op = action_type.split(".", 1)[1]
        timeout = self._optional_int(action.get("timeout"))

        if op == "goto":
            url = self._resolve_string(action["url"])
            await driver.goto(
                url,
                wait_until=action.get("wait_until", "load"),
                timeout=timeout or 30000,
            )
            return await self._browser_context()

        if op == "get_title":
            title = await driver.get_title()
            self._store_output(action, title)
            context = await self._browser_context()
            context.update({"title": title, "text": title, "last_text": title})
            return context

        if op == "get_text":
            locator = self._locator_from_selector(page, action["selector"])
            text = await locator.inner_text(timeout=timeout or 10000)
            self._store_output(action, text)
            context = await self._browser_context()
            context.update({"text": text, "last_text": text})
            return context

        if op == "click":
            await self._locator_from_selector(page, action["selector"]).click(
                timeout=timeout or 10000
            )
            return await self._browser_context()

        if op == "fill":
            value = self._resolve_string(str(action.get("value", "")))
            await self._locator_from_selector(page, action["selector"]).fill(
                value, timeout=timeout or 10000
            )
            return await self._browser_context()

        if op == "wait_for":
            state = action.get("state", "visible")
            await self._locator_from_selector(page, action["selector"]).wait_for(
                state=state,
                timeout=timeout or 10000,
            )
            return await self._browser_context()

        if op == "wait_for_url":
            expected = self._resolve_string(str(action.get("url") or action.get("value")))
            await page.wait_for_url(expected, timeout=timeout or 10000)
            return await self._browser_context()

        if op == "press":
            key = str(action["key"])
            if action.get("selector"):
                await self._locator_from_selector(page, action["selector"]).press(
                    key, timeout=timeout or 10000
                )
            else:
                await page.keyboard.press(key)
            return await self._browser_context()

        if op == "select_option":
            value = self._resolve_string(str(action.get("value", "")))
            await self._locator_from_selector(page, action["selector"]).select_option(
                value,
                timeout=timeout or 10000,
            )
            return await self._browser_context()

        if op == "check":
            await self._locator_from_selector(page, action["selector"]).check(
                timeout=timeout or 10000
            )
            return await self._browser_context()

        if op == "uncheck":
            await self._locator_from_selector(page, action["selector"]).uncheck(
                timeout=timeout or 10000
            )
            return await self._browser_context()

        raise RuntimeError(f"Unsupported browser action: {action_type}")

    async def _execute_api_action(self, action_type: str, action: dict) -> Dict[str, Any]:
        driver = await self._get_api_driver()
        method = action_type.split(".", 1)[1].upper()
        target = self._resolve_api_target(action)
        headers = self._resolve_structure(action.get("headers", {})) or None
        params = self._resolve_structure(action.get("params", {})) or None
        json_data = (
            self._resolve_structure(action.get("json_data")) if "json_data" in action else None
        )

        if method == "GET":
            response = await driver.get(target, params=params, headers=headers)
        elif method == "DELETE":
            response = await driver.delete(target, params=params, headers=headers)
        else:
            response = await driver._request(
                method,
                target,
                json=json_data,
                params=params,
                headers=headers,
            )

        context = self._api_response_context(response)
        self._last_api_context = context
        return context

    def _api_response_context(self, response: Any) -> Dict[str, Any]:
        body = response.text
        try:
            response_json = response.json()
        except Exception:
            response_json = None

        return {
            "status_code": response.status_code,
            "response_body": body,
            "response_json": response_json,
            "response_headers": redact_mapping(dict(response.headers), self._secret_values()),
            "body_preview": redacted_preview(body, self._secret_values(), max_chars=4096),
            "url": sanitize_url(str(response.url)),
        }

    async def _execute_desktop_action(self, action_type: str, action: dict) -> Dict[str, Any]:
        driver = await self._get_desktop_driver(action)
        op = action_type.split(".", 1)[1]
        timeout = self._optional_int(action.get("timeout")) or self.config.element_find_timeout

        if op == "launch":
            app_path = self._resolve_string(str(action.get("app_path") or action.get("path")))
            await driver.launch_app(
                app_path=app_path,
                app_name=action.get("app_name"),
                wait_for_window=bool(action.get("wait_for_window", True)),
                timeout=timeout,
            )
            window_title = action.get("window_title")
            if window_title:
                await driver.connect_to_app(title=str(window_title), timeout=timeout)
            return {
                "window_exists": True,
                "window_title": window_title or action.get("app_name") or app_path,
                "current_window": window_title or action.get("app_name") or app_path,
            }

        if op == "attach":
            window_title = self._resolve_string(str(action.get("window_title", ""))) if action.get("window_title") else None
            class_name = self._resolve_string(str(action.get("class_name", ""))) if action.get("class_name") else None
            await driver.connect_to_app(title=window_title, class_name=class_name, timeout=timeout)
            return {
                "window_exists": True,
                "window_title": window_title or class_name,
                "current_window": window_title or class_name,
            }

        if op == "click":
            selector = await self._desktop_selector_for_action(driver, action.get("selector", {}))
            element = None if "coordinates" in selector else await driver.find_element(timeout=timeout, **selector)
            if element is None:
                if "coordinates" not in selector:
                    raise RuntimeError(f"Desktop element not found: {selector}")
            await driver.click(timeout=timeout, **selector)
            return {
                "element_exists": True,
                "elements": [element.to_dict()] if element else [],
                "selector_visible": True,
                "selector_quality": "coordinate_fallback" if "coordinates" in selector else "strong",
            }

        if op == "get_text":
            selector = self._desktop_selector(action.get("selector", {}))
            text = await driver.get_text(timeout=timeout, **selector)
            if text is None:
                raise RuntimeError(f"Desktop text element not found: {selector}")
            self._store_output(action, text)
            return {
                "element_exists": True,
                "element_text": text,
                "text": text,
                "last_text": text,
            }

        if op == "type":
            selector = self._desktop_selector(action.get("selector", {})) if action.get("selector") else {}
            text = self._resolve_string(str(action.get("text", "")))
            await driver.type_keys(text=text, timeout=timeout, **selector)
            return {
                "field_value": text,
                "last_text": text,
                "selector_visible": True if selector else None,
            }

        if op == "clipboard_paste":
            selector = self._desktop_selector(action.get("selector", {})) if action.get("selector") else {}
            if selector:
                element = await driver.find_element(timeout=timeout, **selector)
                if element is None:
                    raise RuntimeError(f"Desktop element not found: {selector}")
                await driver.click(timeout=timeout, **selector)
            text = self._desktop_clipboard_text(action)
            from harness.desktop.clipboard import ClipboardPaste

            factory = getattr(self, "_clipboard_paste_factory", ClipboardPaste)
            factory().paste_text(text)
            return {
                "clipboard_paste": True,
                "field_value": "[REDACTED]" if action.get("secret") else text,
                "selector_visible": True if selector else None,
                "secret_redacted": bool(action.get("secret")),
            }

        if op == "press":
            keys = self._resolve_string(str(action.get("keys", "")))
            await driver.press_keys(keys)
            return {"keys_pressed": keys, "last_text": keys}

        if op == "menu_select":
            path = self._resolve_string(str(action.get("path", "")))
            if not hasattr(driver, "menu_select"):
                raise RuntimeError(f"{getattr(driver, 'driver_type', 'desktop')} does not support menu_select")
            await driver.menu_select(path)
            return {"menu_path": path, "window_exists": True}

        if op == "wait":
            selector = self._desktop_selector(action.get("selector", {})) if action.get("selector") else None
            if selector:
                element = await driver.find_element(timeout=timeout, **selector)
                if element is None:
                    raise RuntimeError(f"Desktop wait element not found: {selector}")
                return {"element_exists": True, "elements": [element.to_dict()], "selector_visible": True}
            if action.get("window_title") or action.get("class_name"):
                window_title = (
                    self._resolve_string(str(action.get("window_title", "")))
                    if action.get("window_title")
                    else None
                )
                class_name = (
                    self._resolve_string(str(action.get("class_name", "")))
                    if action.get("class_name")
                    else None
                )
                await driver.connect_to_app(title=window_title, class_name=class_name, timeout=timeout)
                return {"window_exists": True, "window_title": window_title or class_name}
            text = self._resolve_string(str(action.get("text", "")))
            found_text = await self._desktop_wait_for_text(driver, text, timeout=timeout)
            return {"last_text": found_text, "text": found_text}

        if op == "screenshot":
            path = await driver.screenshot(name=action.get("name"))
            self._store_output(action, path)
            return {"screenshot": path, "file_path": path}

        if op == "dump_tree":
            max_depth = self._optional_int(action.get("max_depth")) or 3
            tree = await driver.dump_tree(max_depth=max_depth)
            self._store_output(action, tree)
            driver_type = str(getattr(driver, "driver_type", "")).lower()
            tree_key = "win32_tree" if "win32" in driver_type else "uia_tree"
            return {"tree": tree, tree_key: tree, "last_text": json.dumps(tree, default=str)}

        if op in {"ocr_read", "ocr_wait"}:
            image = await self._desktop_ocr_image(driver, action)
            from harness.desktop.ocr import OcrEngine

            engine = OcrEngine(os.getenv("RPA_OCR_COMMAND"))
            if op == "ocr_wait":
                result = engine.wait_for_text(
                    image,
                    self._resolve_string(str(action.get("text", ""))),
                    secret_values=self._secret_values(),
                    timeout=timeout,
                )
            else:
                result = engine.read_image(
                    image,
                    secret_values=self._secret_values(),
                    timeout=timeout,
                )
            text = str(result.get("text", ""))
            self._store_output(action, text)
            ocr_artifact = None
            if self.failure._run_dir:
                payload = {
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "matched": result.get("matched"),
                    "image": result.get("image") or str(image),
                    "region": action.get("region"),
                    "text": text,
                }
                ocr_artifact = self._relative_evidence_path(
                    self.failure.save_artifact(
                        f"ocr_result_{int(time.time() * 1000)}.json",
                        json.dumps(redact_value(payload), indent=2, default=str),
                    )
                )
            return {
                "ocr_status": result.get("status"),
                "ocr_reason": result.get("reason"),
                "ocr_text": text,
                "text": text,
                "last_text": text,
                "screenshot": result.get("image") or str(image),
                "ocr_artifact": ocr_artifact,
                "region": action.get("region"),
                "matched": result.get("matched"),
            }

        if op == "close":
            await driver.close_app()
            return {"status": "ok"}

        raise RuntimeError(f"Unsupported desktop action: {action_type}")

    async def _execute_excel_action(self, action_type: str, action: dict) -> Dict[str, Any]:
        from harness.rpa.excel import ExcelHandler

        op = action_type.split(".", 1)[1]
        path = self._resolve_string(str(action.get("path") or action.get("file_path")))
        sheet = self._resolve_string(str(action.get("sheet"))) if action.get("sheet") else None

        if op == "read":
            excel = ExcelHandler(path, create_if_missing=False)
            try:
                rows = [
                    {
                        "row_number": row.row_number,
                        "data": row.data,
                        "raw_values": row.raw_values,
                    }
                    for row in excel.iter_rows(
                        sheet=sheet,
                        header_row=int(action.get("header_row", 1)),
                        min_row=self._optional_int(action.get("min_row")),
                        max_row=self._optional_int(action.get("max_row")),
                        columns=action.get("columns"),
                    )
                ]
                self._store_output(action, rows)
                return {
                    "workbook": None,
                    "workbook_path": str(excel.file_path),
                    "file_path": str(excel.file_path),
                    "sheet_name": sheet,
                    "sheet_names": excel.sheet_names(),
                    "rows": rows,
                    "row_count": len(rows),
                }
            finally:
                excel.close()

        excel = ExcelHandler(path, create_if_missing=True)
        try:
            if op == "write":
                if action.get("cell"):
                    excel.write_cell(
                        sheet=sheet,
                        cell=str(action["cell"]),
                        value=self._resolve_structure(action.get("value")),
                    )
                if action.get("headers") or action.get("rows"):
                    excel.write_rows(
                        sheet=sheet,
                        headers=self._resolve_structure(action.get("headers", [])),
                        rows=self._resolve_structure(action.get("rows", [])),
                        start_row=int(action.get("start_row", 1)),
                    )
                excel.save()
            elif op == "append_row":
                excel.append_row(
                    sheet=sheet,
                    row_data=self._resolve_structure(action.get("row_data")),
                    mapping=self._resolve_structure(action.get("mapping")),
                    headers=self._resolve_structure(action.get("headers")),
                )
                excel.save()
            else:
                raise RuntimeError(f"Unsupported excel action: {action_type}")

            self._store_output(action, str(excel.file_path))
            return {
                "workbook": None,
                "workbook_path": str(excel.file_path),
                "file_path": str(excel.file_path),
                "sheet_name": sheet,
                "sheet_names": excel.sheet_names(),
                "output_files": [str(excel.file_path)],
            }
        finally:
            excel.close()

    async def _verify_step(
        self, step: dict, action_result: Dict[str, Any]
    ) -> List[VerificationResult]:
        results: List[VerificationResult] = []
        action_type = step.get("action", {}).get("type", "no_op")
        if (
            not step.get("success_check")
            and step.get("allow_without_success_check")
            and action_type == "no_op"
        ):
            return [
                VerificationResult(
                    passed=True,
                    check_type=CheckType.ALWAYS_PASS,
                    expected="allowed no-op",
                    actual="passed",
                )
            ]

        for raw_check in step.get("success_check", []) or []:
            check_data = self._resolve_structure(raw_check)
            check = SuccessCheck.from_dict(check_data)

            if self._is_browser_check(check.type) and self._drivers.get("browser"):
                results.append(await self._verify_browser_check(step, check))
            elif self._is_api_check(check.type):
                if not action_type.startswith("api."):
                    results.append(
                        VerificationResult(
                            passed=False,
                            check_type=check.type,
                            expected=check.value,
                            actual=None,
                            message="API checks only apply to the current API action",
                        )
                    )
                else:
                    results.append(self._run_context_check(check, action_result))
            else:
                context = dict(self._variables)
                context.update(action_result)
                results.append(self._run_context_check(check, context))

        return results

    async def _verify_browser_check(self, step: dict, check: SuccessCheck) -> VerificationResult:
        driver = self._drivers["browser"]
        page = driver.page
        expected = check.value

        if check.type == CheckType.URL_CONTAINS:
            current_url = page.url
            passed = str(expected) in current_url
            return VerificationResult(
                passed=passed,
                check_type=check.type,
                expected=expected,
                actual=sanitize_url(current_url),
                message="" if passed else f"URL does not contain '{expected}'",
            )

        if check.type == CheckType.URL_EQUALS:
            current_url = page.url
            passed = current_url == str(expected)
            return VerificationResult(
                passed=passed,
                check_type=check.type,
                expected=expected,
                actual=sanitize_url(current_url),
                message="" if passed else "URL mismatch",
            )

        if check.type == CheckType.VISIBLE_TEXT:
            body = await page.locator("body").inner_text(timeout=5000)
            passed = str(expected) in body
            return VerificationResult(
                passed=passed,
                check_type=check.type,
                expected=expected,
                actual=redacted_preview(body, self._secret_values(), max_chars=500),
                message="" if passed else f"Text not visible: '{expected}'",
            )

        if check.type in {CheckType.SELECTOR_VISIBLE, CheckType.SELECTOR_HIDDEN}:
            selector = check.selector or step.get("action", {}).get("selector")
            locator = self._locator_from_selector(page, selector)
            try:
                visible = await locator.is_visible(timeout=5000)
            except Exception:
                visible = False
            passed = visible if check.type == CheckType.SELECTOR_VISIBLE else not visible
            return VerificationResult(
                passed=passed,
                check_type=check.type,
                expected="element visible"
                if check.type == CheckType.SELECTOR_VISIBLE
                else "element hidden",
                actual=str(visible),
                message="" if passed else f"Selector visibility check failed: {selector}",
            )

        if check.type == CheckType.FIELD_HAS_VALUE:
            selector = check.selector or step.get("action", {}).get("selector")
            locator = self._locator_from_selector(page, selector)
            value = await locator.input_value(timeout=5000)
            has_value = value != ""
            return VerificationResult(
                passed=has_value,
                check_type=check.type,
                expected="[REDACTED]" if check.redacted else "non-empty",
                actual="[REDACTED]"
                if check.redacted
                else redacted_preview(value, self._secret_values(), 100),
                message="Field has value" if has_value else "Field has no value",
                evidence={"redacted": bool(check.redacted)},
            )

        return self._run_context_check(check, {})

    def _run_context_check(
        self, check: SuccessCheck, context: Dict[str, Any]
    ) -> VerificationResult:
        runner = CheckRunner()
        for key, value in context.items():
            runner.set_context(key, value)
        return runner.run(check)

    async def _get_browser_driver(self):
        if "browser" in self._drivers:
            return self._drivers["browser"]

        from harness.drivers.playwright import PlaywrightDriver

        try:
            driver = await PlaywrightDriver.launch(config=self.config)
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                raise RuntimeError(
                    "Browser YAML runtime requires Playwright. Install it with: "
                    "python3 -m pip install playwright && python3 -m playwright install chromium"
                ) from exc
            raise
        self._drivers["browser"] = driver
        self._attach_browser_evidence_handlers(driver)
        return driver

    async def _get_api_driver(self):
        if "api" in self._drivers:
            return self._drivers["api"]

        from harness.drivers.api import APIDriver

        driver = APIDriver(config=self.config)
        await driver.launch()
        self._drivers["api"] = driver
        return driver

    async def _get_desktop_driver(self, action: dict | None = None):
        backend = self._desktop_backend(action or {})
        key = f"desktop:{backend}"
        if key in self._drivers:
            return self._drivers[key]
        if backend == "uia" and "desktop" in self._drivers:
            return self._drivers["desktop"]

        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError(
                "Desktop YAML runtime requires Windows UIAutomation on Windows; "
                f"current platform is {sys.platform}."
            )

        if backend == "win32":
            from harness.drivers.win32_ui import Win32UIDriver

            driver = Win32UIDriver(config=self.config)
            if not getattr(driver, "_win32gui", None):
                raise RuntimeError(
                    "Desktop YAML runtime requires pywin32. Install the Windows optional "
                    "dependencies before running Win32 desktop workflows."
                )
        else:
            from harness.drivers.windows_ui import WindowsUIDriver

            driver = WindowsUIDriver(config=self.config)
            if not getattr(driver, "_pywinauto", None):
                raise RuntimeError(
                    "Desktop YAML runtime requires pywinauto. Install the Windows optional "
                    "dependencies before running desktop workflows."
                )
            self._drivers["desktop"] = driver
        self._drivers[key] = driver
        return driver

    def _desktop_backend(self, action: dict) -> str:
        selector = action.get("selector") if isinstance(action.get("selector"), dict) else {}
        backend = str(action.get("backend") or selector.get("backend") or "").lower()
        strategy = str(selector.get("strategy") or "").lower()
        if backend == "win32" or strategy.startswith("win32_") or strategy in {
            "hwnd",
            "class_name+name",
            "class_name+control_type",
        }:
            return "win32"
        return "uia"

    async def _desktop_selector_for_action(self, driver: Any, selector: dict) -> Dict[str, Any]:
        if str((selector or {}).get("strategy") or "").lower() != "coordinate":
            return self._desktop_selector(selector)
        if not getattr(self.config, "allow_coordinate_fallback", False):
            raise RuntimeError("Coordinate desktop selector requires allow_coordinate_fallback=True")
        value = selector.get("value") if isinstance(selector.get("value"), dict) else {}
        if "x" in value or "y" in value:
            raise RuntimeError("Absolute desktop coordinates are rejected; use x_ratio/y_ratio")
        if "x_ratio" not in value or "y_ratio" not in value:
            raise RuntimeError("Coordinate desktop selector requires x_ratio and y_ratio")
        if not hasattr(driver, "window_rect"):
            raise RuntimeError("Coordinate desktop selector requires driver.window_rect")
        left, top, width, height = await driver.window_rect()
        return {
            "coordinates": (
                int(left + (float(value["x_ratio"]) * width)),
                int(top + (float(value["y_ratio"]) * height)),
            )
        }

    async def _desktop_wait_for_text(self, driver: Any, expected: str, timeout: int) -> str:
        deadline = time.time() + timeout
        last_text = ""
        while time.time() < deadline:
            tree = await driver.dump_tree(max_depth=3)
            last_text = json.dumps(tree, default=str)
            if expected in last_text:
                return last_text
            time.sleep(0.2)
        raise RuntimeError(f"Desktop text not found before timeout: {expected}")

    def _desktop_clipboard_text(self, action: dict) -> str:
        if action.get("secret"):
            secret_ref = str(action.get("secret"))
            if secret_ref in self._secrets:
                return self._secrets[secret_ref].reveal()
            return self._resolve_string(secret_ref)
        return self._resolve_string(str(action.get("text", "")))

    async def _desktop_ocr_image(self, driver: Any, action: dict) -> Path:
        if action.get("screenshot"):
            return Path(self._resolve_string(str(action["screenshot"])))
        path = Path(await driver.screenshot(name=action.get("name") or "desktop_ocr.png"))
        region = action.get("region") if isinstance(action.get("region"), dict) else {}
        if {"x_ratio", "y_ratio", "width_ratio", "height_ratio"}.issubset(region):
            try:
                from PIL import Image

                image = Image.open(path)
                width, height = image.size
                box = (
                    int(float(region["x_ratio"]) * width),
                    int(float(region["y_ratio"]) * height),
                    int((float(region["x_ratio"]) + float(region["width_ratio"])) * width),
                    int((float(region["y_ratio"]) + float(region["height_ratio"])) * height),
                )
                cropped = path.with_name(path.stem + "_ocr_region" + path.suffix)
                image.crop(box).save(cropped)
                return cropped
            except Exception:
                return path
        return path

    def _attach_browser_evidence_handlers(self, driver):
        page = driver.page

        def on_console(message):
            try:
                if message.type == "error":
                    self._console_entries.append(
                        {
                            "type": message.type,
                            "text": redacted_preview(message.text, self._secret_values(), 500),
                        }
                    )
            except Exception:
                pass

        def on_request_failed(request):
            try:
                failure = request.failure
                if callable(failure):
                    failure = failure()
                error_text = (
                    failure.get("errorText", "")
                    if isinstance(failure, dict)
                    else str(failure or "")
                )
                self._network_entries.append(
                    {
                        "url": sanitize_url(request.url),
                        "method": request.method,
                        "error_text": redact_text(error_text, self._secret_values(), 300),
                    }
                )
            except Exception:
                pass

        def on_response(response):
            try:
                if response.status >= 400:
                    self._network_entries.append(
                        {
                            "url": sanitize_url(response.url),
                            "status": response.status,
                        }
                    )
            except Exception:
                pass

        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

    def _locator_from_selector(self, page, selector: dict):
        if not isinstance(selector, dict):
            raise ValueError("selector must be an object")

        strategy = str(selector.get("strategy", "")).lower()
        value = (
            self._resolve_string(str(selector.get("value", "")))
            if selector.get("value") is not None
            else ""
        )

        if strategy in {"data-testid", "testid"}:
            return page.get_by_test_id(value)
        if strategy == "role":
            role = selector.get("role") or value
            name = selector.get("name")
            return page.get_by_role(role, name=name) if name else page.get_by_role(role)
        if strategy == "label":
            return page.get_by_label(value)
        if strategy == "placeholder":
            return page.get_by_placeholder(value)
        if strategy == "text":
            return page.get_by_text(value)
        if strategy == "id":
            return page.locator(f"[id={json.dumps(value)}]")
        if strategy == "name":
            return page.locator(f"[name={json.dumps(value)}]")
        if strategy == "aria-label":
            return page.locator(f"[aria-label={json.dumps(value)}]")
        if strategy == "data-test":
            return page.locator(f"[data-test={json.dumps(value)}]")
        if strategy == "data-qa":
            return page.locator(f"[data-qa={json.dumps(value)}]")
        if strategy == "css":
            return page.locator(value)
        if strategy == "xpath":
            return page.locator(value if value.startswith("xpath=") else f"xpath={value}")

        raise ValueError(f"Unsupported selector strategy: {strategy}")

    def _desktop_selector(self, selector: dict) -> Dict[str, Any]:
        if not isinstance(selector, dict):
            raise ValueError("selector must be an object")

        strategy = str(selector.get("strategy", "")).lower()
        value = (
            self._resolve_string(str(selector.get("value", "")))
            if selector.get("value") is not None
            else ""
        )

        if strategy in {"automation_id", "auto_id", "id"}:
            return {"automation_id": value}
        if strategy == "name":
            return {"name": value}
        if strategy == "class_name":
            return {"class_name": value}
        if strategy == "control_type":
            return {"control_type": value}
        if strategy == "name+control_type":
            return {
                "name": self._resolve_string(str(selector.get("name", ""))),
                "control_type": self._resolve_string(str(selector.get("control_type", ""))),
            }
        if strategy == "win32_control_id":
            return {"control_id": value}
        if strategy == "hwnd":
            return {"hwnd": value}
        if strategy == "class_name+name":
            return {
                "class_name": self._resolve_string(str(selector.get("class_name", ""))),
                "name": self._resolve_string(str(selector.get("name", ""))),
            }
        if strategy == "class_name+control_type":
            return {
                "class_name": self._resolve_string(str(selector.get("class_name", ""))),
                "control_type": self._resolve_string(str(selector.get("control_type", ""))),
            }

        raise ValueError(f"Unsupported desktop selector strategy: {strategy}")

    async def _browser_context(self) -> Dict[str, Any]:
        driver = self._drivers["browser"]
        return {
            "current_url": sanitize_url(driver.page.url),
            "url": sanitize_url(driver.page.url),
        }

    def _resolve_api_target(self, action: dict) -> str:
        if action.get("url"):
            return self._resolve_string(str(action["url"]))

        path = self._resolve_string(str(action.get("path", "")))
        if path.startswith("http://") or path.startswith("https://"):
            return path

        base_url = self._resolve_string(
            str(action.get("base_url") or self._inputs.get("api_base_url", ""))
        )
        if not base_url:
            return path
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _resolve_inputs(self, inputs: dict) -> Dict[str, Any]:
        resolved = dict(self.config.variables)
        for key, value in (inputs or {}).items():
            resolved[key] = os.path.expandvars(str(value)) if isinstance(value, str) else value
        return resolved

    def _resolve_secret_env_names(self, credentials: dict) -> Dict[str, str]:
        return {str(key): str(value) for key, value in (credentials or {}).items()}

    def _missing_secrets(self) -> List[dict]:
        missing = []
        for logical_name, env_name in self._secret_env_names.items():
            if os.getenv(env_name) is None:
                missing.append({"name": logical_name, "env": env_name})
        return missing

    def _load_secrets(self) -> Dict[str, SecretValue]:
        return {
            logical_name: SecretValue(logical_name, os.environ[env_name])
            for logical_name, env_name in self._secret_env_names.items()
        }

    def _resolve_structure(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {key: self._resolve_structure(child) for key, child in value.items()}
        if isinstance(value, list):
            return [self._resolve_structure(child) for child in value]
        return value

    def _resolve_string(self, value: str) -> str:
        result = value
        cwd = Path.cwd().resolve()

        def replace_pwd(text: str) -> str:
            text = text.replace("file://${PWD}", cwd.as_uri())
            text = FILE_PWD_REF_RE.sub(cwd.as_uri(), text)
            text = text.replace("${PWD}", cwd.as_posix())
            return PWD_REF_RE.sub(cwd.as_posix(), text)

        result = replace_pwd(result)

        def replace_input(match):
            return str(self._inputs.get(match.group(1), match.group(0)))

        def replace_variable(match):
            return str(self._variables.get(match.group(1), match.group(0)))

        def replace_secret(match):
            name = match.group(1)
            if name not in self._secrets:
                raise RuntimeError(f"Secret '{name}' is not available")
            return self._secrets[name].reveal()

        result = INPUT_REF_RE.sub(replace_input, result)
        result = VARIABLE_REF_RE.sub(replace_variable, result)
        result = SECRET_REF_RE.sub(replace_secret, result)
        result = replace_pwd(result)
        return os.path.expandvars(result)

    def _store_output(self, action: dict, value: Any):
        output_name = action.get("output")
        if output_name:
            self._variables[str(output_name)] = value

    def _unsupported_runtime_actions(self, workflow: dict) -> List[str]:
        unsupported = []
        for step in workflow.get("steps", []):
            action_type = step.get("action", {}).get("type", "no_op")
            if action_type == "no_op":
                continue
            if not action_type.startswith(SUPPORTED_RUNTIME_PREFIXES):
                unsupported.append(action_type)
        return unsupported

    def _selected_steps(
        self,
        workflow: dict,
        phase: Optional[str],
        only_record: Optional[str] = None,
    ) -> List[dict]:
        steps = list(workflow.get("steps", []) or [])
        if phase:
            steps = [step for step in steps if self._step_phase(step) == phase]
        if only_record:
            steps = [step for step in steps if str(step.get("record_id") or "") == str(only_record)]
        return steps

    def _selection_error(
        self,
        workflow: dict,
        phase: Optional[str],
        pause_before: Optional[str],
        pause_after_phase: Optional[str],
        until_step: Optional[str],
        only_record: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> Optional[str]:
        steps = list(workflow.get("steps", []) or [])
        phases = {self._step_phase(step) for step in steps}
        step_ids = {str(step.get("id")) for step in steps}
        record_ids = {str(step.get("record_id")) for step in steps if step.get("record_id")}
        if only_record and not record_ids:
            plan = build_execution_plan(workflow, inputs=inputs or workflow.get("inputs", {}))
            record_ids = {
                str(unit.step.get("record_id"))
                for unit in plan.units
                if unit.step.get("record_id")
            }
        if phase and phase not in phases:
            return f"Unknown phase: {phase}"
        if only_record and str(only_record) not in record_ids:
            return f"Unknown record: {only_record}"
        if pause_after_phase and pause_after_phase not in phases:
            return f"Unknown phase: {pause_after_phase}"
        for label, step_id in (("--pause-before", pause_before), ("--until-step", until_step)):
            if step_id and step_id not in step_ids:
                return f"{label} references unknown step: {step_id}"
        return None

    @staticmethod
    def _step_phase(step: dict) -> str:
        return str(step.get("phase") or step.get("current_stage") or "default")

    def _paused_result(
        self,
        workflow: dict,
        step: dict,
        steps: List[Dict[str, Any]],
        rulebook_audit: dict,
        started_at: str,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "status": "paused",
            "manifest_status": "blocked",
            "failure_type": "paused",
            "reason": reason,
            "workflow_id": workflow["id"],
            "workflow_name": workflow.get("name", workflow["id"]),
            "phase": self._step_phase(step),
            "step": step.get("id"),
            "action": redact_mapping(step.get("action", {}), self._secret_values()),
            "success_checks": redact_value(step.get("success_check", [])),
            "side_effect": step.get("side_effect"),
            "safe_retry": self._safe_retry(step, step.get("action", {}).get("type", "no_op")),
            "steps": steps,
            "duration_ms": (self._parse_time(self._now()) - self._parse_time(started_at)) * 1000,
            "rulebook_audit": rulebook_audit,
            "run_id": self.failure._current_run_id,
            "run_dir": str(self.failure._run_dir.resolve()) if self.failure._run_dir else "",
        }

    def _copilot_enabled(self) -> bool:
        return bool(getattr(self.config, "copilot_enabled", False))

    def _get_copilot(self) -> CopilotCheckpoint:
        if self._copilot is None:
            self._copilot = CopilotCheckpoint(self.failure._run_dir or Path("runs"))
        return self._copilot

    async def _ask_copilot(
        self,
        workflow: dict,
        step: dict,
        phase: str,
        *,
        reason: str,
    ) -> dict:
        question = (
            f"Workflow '{workflow.get('name', workflow.get('id'))}' is paused "
            f"before step '{step.get('id')}'. Continue?"
        )
        self._timeline(
            workflow,
            "copilot.question",
            status="waiting",
            phase=phase,
            step_id=step.get("id"),
            message=question,
        )
        result = await self._get_copilot().ask(
            workflow=workflow,
            step=step,
            reason=reason,
            run_id=self.failure._current_run_id,
            drivers=self._drivers,
            secret_values=self._secret_values(),
            question=question,
        )
        self._timeline(
            workflow,
            "copilot.answer",
            status=result.get("action"),
            phase=phase,
            step_id=step.get("id"),
            message=result.get("answer"),
        )
        return result

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_time(value: str) -> float:
        return datetime.fromisoformat(value).timestamp()

    def _timeline(self, workflow: dict, event: str, **fields: Any) -> None:
        if not self.failure._run_dir:
            return
        entry = {
            "timestamp": self._now(),
            "run_id": self.failure._current_run_id,
            "workflow": workflow.get("id"),
            "event": event,
        }
        entry.update({key: value for key, value in fields.items() if value is not None})
        with open(self.failure._run_dir / "timeline.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact_value(entry), default=str) + "\n")

    def _record_step(
        self,
        workflow: dict,
        step: dict,
        status: str,
        *,
        step_result: Optional[dict] = None,
        evidence_bundle: Optional[str] = None,
    ) -> None:
        if not self.failure._run_dir or not step.get("record_id"):
            return
        result = step_result or {}
        entry = {
            "schema_version": 1,
            "run_id": self.failure._current_run_id,
            "workflow": workflow.get("id"),
            "record_id": step.get("record_id"),
            "row_number": step.get("row_number"),
            "phase": self._step_phase(step),
            "status": status,
            "failed_step": step.get("id") if status == "failed" else None,
            "failure_kind": result.get("failure_kind"),
            "evidence_bundle": evidence_bundle,
            "retry_count": max(int(result.get("attempts", 1) or 1) - 1, 0),
            "safe_retry": result.get("safe_retry") or self._safe_retry(
                step, step.get("action", {}).get("type", "no_op")
            ),
            "external_reference": result.get("external_reference"),
            "timestamp": self._now(),
        }
        with open(self.failure._run_dir / "records.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(redact_value(entry), default=str) + "\n")

    def _record_summary(self) -> dict:
        if not self.failure._run_dir:
            return {}
        latest: dict[str, dict] = {}
        for entry in read_jsonl(self.failure._run_dir / "records.jsonl"):
            record_id = str(entry.get("record_id") or "")
            if record_id:
                latest[record_id] = entry
        return {
            "total_records": len(latest),
            "passed_records": sum(1 for item in latest.values() if item.get("status") == "passed"),
            "failed_records": sum(1 for item in latest.values() if item.get("status") == "failed"),
            "skipped_records": sum(1 for item in latest.values() if item.get("status") == "skipped"),
        }

    def _write_manifest(
        self,
        workflow: dict,
        status: str,
        *,
        started_at: str,
        finished_at: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> None:
        if not self.failure._run_dir:
            return
        steps = list(workflow.get("steps", []) or [])
        result_steps = list((result or {}).get("steps", []) or [])
        summary = {
            "total_phases": len({self._step_phase(step) for step in steps}),
            "passed_phases": len({step.get("phase") for step in result_steps if step.get("status") == "passed"}),
            "failed_phases": len({step.get("phase") for step in result_steps if step.get("status") == "failed"}),
            "total_steps": len(steps),
            "passed_steps": sum(1 for step in result_steps if step.get("status") == "passed"),
            "failed_steps": sum(1 for step in result_steps if step.get("status") == "failed"),
            "total_records": 0,
            "passed_records": 0,
            "failed_records": 0,
            "skipped_records": 0,
        }
        summary.update(self._record_summary())
        manifest = {
            "schema_version": 1,
            "run_id": self.failure._current_run_id,
            "workflow": workflow.get("id"),
            "workflow_path": self._workflow_path,
            "input_file": self._first_input_file(workflow),
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "report": "report.html",
            "timeline": "timeline.jsonl",
            "records": "records.jsonl" if (self.failure._run_dir / "records.jsonl").exists() else None,
            "preflight": "preflight.json",
            "run_directory": str(self.failure._run_dir.resolve()),
            "redaction": {"status": "passed"},
            "summary": summary,
        }
        (self.failure._run_dir / "run_manifest.json").write_text(
            json.dumps(redact_value(manifest), indent=2, default=str),
            encoding="utf-8",
        )

    def _write_preflight(self, preflight: dict, workflow: dict, started_at: str) -> None:
        if not self.failure._run_dir:
            return
        payload = {
            "schema_version": 1,
            "run_id": self.failure._current_run_id,
            "workflow": workflow.get("id"),
            "status": preflight.get("status"),
            "checks": [
                {
                    "name": check.get("name"),
                    "status": "passed" if check.get("passed") else "failed",
                    "message": check.get("path") or "",
                    "blocking": not check.get("passed"),
                }
                for check in [
                    *preflight.get("passed_checks", []),
                    *[
                        {"name": error, "passed": False}
                        for error in preflight.get("blocking_errors", [])
                    ],
                ]
            ],
            "warnings": preflight.get("warnings", []),
            "started_at": started_at,
            "finished_at": self._now(),
        }
        (self.failure._run_dir / "preflight.json").write_text(
            json.dumps(redact_value(payload), indent=2, default=str),
            encoding="utf-8",
        )

    def _write_redacted_workflow(self, workflow: dict) -> None:
        if self.failure._run_dir:
            (self.failure._run_dir / "workflow_resolved.redacted.yaml").write_text(
                yaml.safe_dump(redact_value(workflow), sort_keys=False),
                encoding="utf-8",
            )

    def _write_run_report(self, workflow: dict, result: dict) -> None:
        if not self.failure._run_dir:
            return
        run_dir = self.failure._run_dir
        manifest = read_json(run_dir / "run_manifest.json")
        preflight = read_json(run_dir / "preflight.json")
        timeline = read_jsonl(run_dir / "timeline.jsonl")
        records = read_jsonl(run_dir / "records.jsonl")
        report = {
            "schema_version": 1,
            "manifest": manifest,
            "preflight": preflight,
            "timeline": timeline,
            "records": records,
            "steps": result.get("steps", []),
            "failure_kind_summary": self._failure_kind_summary(result.get("steps", []), timeline),
            "failure_report": self._relative_to_run(result.get("failure_report")),
            "reason": result.get("reason"),
        }
        (run_dir / "report.json").write_text(
            json.dumps(redact_value(report), indent=2, default=str),
            encoding="utf-8",
        )
        (run_dir / "report.html").write_text(
            self._run_report_html(workflow, report),
            encoding="utf-8",
        )

    def _run_report_html(self, workflow: dict, report: dict) -> str:
        manifest = report.get("manifest") or {}
        steps = report.get("steps") or []
        timeline = report.get("timeline") or []
        failures = [step for step in steps if step.get("status") == "failed"]
        phase_rows = self._phase_rows(steps)
        failure_kind_rows = self._failure_kind_rows(report.get("failure_kind_summary") or [])
        record_rows = self._record_rows(report.get("records") or [])
        step_rows = "".join(
            "<tr>"
            f"<td>{self._esc(item.get('timestamp'))}</td>"
            f"<td>{self._esc(item.get('phase'))}</td>"
            f"<td>{self._esc(item.get('step_id'))}</td>"
            f"<td>{self._esc(item.get('action_type'))}</td>"
            f"<td>{self._esc(item.get('status'))}</td>"
            f"<td>{self._esc(item.get('failure_kind'))}</td>"
            f"<td>{self._artifact_link(item.get('evidence_bundle'))}</td>"
            "</tr>"
            for item in timeline
            if str(item.get("event", "")).startswith("step.")
        )
        failure_rows = "".join(
            "<tr>"
            f"<td>{self._esc(step.get('phase'))}</td>"
            f"<td>{self._esc(step.get('step_id'))}</td>"
            f"<td>{self._esc(step.get('failure_kind'))}</td>"
            f"<td>{self._esc((step.get('safe_retry') or {}).get('status'))}</td>"
            f"<td>{self._esc((step.get('safe_retry') or {}).get('reason'))}</td>"
            f"<td>{self._artifact_link('evidence_bundle.json')} {self._artifact_link('repair_packet.json')}</td>"
            f"<td>{self._esc(self._recommendation(step.get('failure_kind')))}</td>"
            "</tr>"
            for step in failures
        ) or "<tr><td colspan='7'>No failed steps.</td></tr>"
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{self._esc(workflow.get('name', workflow.get('id')))} run report</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f6f7f9; color: #17202a; }}
    header {{ background: #1f2937; color: white; padding: 22px 28px; }}
    main {{ padding: 20px 28px; display: grid; gap: 16px; }}
    section {{ background: white; border: 1px solid #d8dde6; border-radius: 6px; padding: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e6e9ef; padding: 8px; vertical-align: top; }}
    .bad {{ color: #b42318; font-weight: 700; }}
    .ok {{ color: #047857; font-weight: 700; }}
    a {{ color: #175cd3; }}
  </style>
</head>
<body>
  <header>
    <h1>{self._esc(workflow.get('name', workflow.get('id')))}</h1>
    <div>Run {self._esc(manifest.get('run_id'))} · {self._esc(manifest.get('status'))}</div>
  </header>
  <main>
    <section><h2>Run summary</h2><table>{self._kv_rows(manifest, ['workflow','status','started_at','finished_at','input_file','timeline','preflight'])}</table></section>
    <section><h2>Phase summary</h2><table><tr><th>Phase</th><th>Status</th><th>Passed steps</th><th>Failed steps</th></tr>{phase_rows}</table></section>
    <section><h2>Step timeline</h2><table><tr><th>Time</th><th>Phase</th><th>Step</th><th>Action</th><th>Status</th><th>Failure kind</th><th>Evidence</th></tr>{step_rows}</table></section>
    {record_rows}
    <section><h2>Failure kind summary</h2><table><tr><th>Failure kind</th><th>Count</th><th>Affected phases</th><th>Affected steps</th><th>Likely area to inspect</th></tr>{failure_kind_rows}</table></section>
    <section><h2>Failed step details</h2><table><tr><th>Phase</th><th>Step</th><th>Failure kind</th><th>Safe retry</th><th>Reason</th><th>Evidence</th><th>Recommended next action</th></tr>{failure_rows}</table></section>
    <section><h2>Preflight</h2><pre>{self._esc(json.dumps(report.get('preflight') or {}, indent=2, default=str))}</pre></section>
  </main>
</body>
</html>"""

    def _phase_rows(self, steps: List[dict]) -> str:
        phases: dict[str, dict[str, int]] = {}
        for step in steps:
            phase = str(step.get("phase") or "default")
            phases.setdefault(phase, {"passed": 0, "failed": 0})
            if step.get("status") == "passed":
                phases[phase]["passed"] += 1
            if step.get("status") == "failed":
                phases[phase]["failed"] += 1
        if not phases:
            return "<tr><td>none</td><td>not run</td><td>0</td><td>0</td></tr>"
        rows = []
        for phase, counts in phases.items():
            status = "failed" if counts["failed"] else "passed"
            rows.append(
                f"<tr><td>{self._esc(phase)}</td><td>{self._esc(status)}</td>"
                f"<td>{counts['passed']}</td><td>{counts['failed']}</td></tr>"
            )
        return "".join(rows)

    def _failure_kind_summary(self, steps: List[dict], timeline: List[dict]) -> List[dict]:
        summary: dict[str, dict[str, Any]] = {}
        sources = [
            {
                "failure_kind": step.get("failure_kind"),
                "phase": step.get("phase"),
                "step_id": step.get("step_id"),
            }
            for step in steps
            if step.get("status") == "failed" and step.get("failure_kind")
        ]
        if not sources:
            sources = [
                item
                for item in timeline
                if item.get("event") == "step.failed" and item.get("failure_kind")
            ]
        for item in sources:
            kind = str(item.get("failure_kind") or "unknown")
            row = summary.setdefault(kind, {"failure_kind": kind, "count": 0, "phases": set(), "steps": set()})
            row["count"] += 1
            if item.get("phase"):
                row["phases"].add(str(item.get("phase")))
            if item.get("step_id"):
                row["steps"].add(str(item.get("step_id")))
        return [
            {
                "failure_kind": kind,
                "count": row["count"],
                "phases": sorted(row["phases"]),
                "steps": sorted(row["steps"]),
                "recommendation": self._recommendation(kind),
            }
            for kind, row in sorted(summary.items())
        ]

    def _failure_kind_rows(self, summary: List[dict]) -> str:
        if not summary:
            return "<tr><td colspan='5'>No failures.</td></tr>"
        return "".join(
            "<tr>"
            f"<td>{self._esc(row.get('failure_kind'))}</td>"
            f"<td>{self._esc(row.get('count'))}</td>"
            f"<td>{self._esc(', '.join(row.get('phases') or []))}</td>"
            f"<td>{self._esc(', '.join(row.get('steps') or []))}</td>"
            f"<td>{self._esc(row.get('recommendation'))}</td>"
            "</tr>"
            for row in summary
        )

    def _record_rows(self, records: List[dict]) -> str:
        if not records:
            return ""
        latest: dict[str, dict] = {}
        for record in records:
            record_id = str(record.get("record_id") or "")
            if record_id:
                latest[record_id] = record
        rows = "".join(
            "<tr>"
            f"<td>{self._esc(record.get('record_id'))}</td>"
            f"<td>{self._esc(record.get('row_number'))}</td>"
            f"<td>{self._esc(record.get('status'))}</td>"
            f"<td>{self._esc(record.get('failed_step'))}</td>"
            f"<td>{self._esc(record.get('failure_kind'))}</td>"
            f"<td>{self._esc((record.get('safe_retry') or {}).get('status'))}</td>"
            f"<td>{self._artifact_link(record.get('evidence_bundle'))}</td>"
            "</tr>"
            for record in latest.values()
        )
        return (
            "<section><h2>Record table</h2><table>"
            "<tr><th>Record</th><th>Row</th><th>Status</th><th>Failed step</th>"
            "<th>Failure kind</th><th>Safe retry</th><th>Evidence</th></tr>"
            f"{rows}</table></section>"
        )

    def _kv_rows(self, payload: dict, keys: List[str]) -> str:
        return "".join(
            f"<tr><td>{self._esc(key)}</td><td>{self._artifact_link(payload.get(key))}</td></tr>"
            for key in keys
        )

    def _artifact_link(self, value: Any) -> str:
        if isinstance(value, str) and value and self.failure._run_dir:
            if (self.failure._run_dir / value).exists():
                return f"<a href='{self._esc(value)}'>{self._esc(value)}</a>"
        return self._esc(value)

    @staticmethod
    def _esc(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    def _relative_to_run(self, path: Any) -> Any:
        if not path or not self.failure._run_dir:
            return path
        try:
            return str(Path(path).resolve().relative_to(self.failure._run_dir.resolve()))
        except Exception:
            return path

    @staticmethod
    def _first_input_file(workflow: dict) -> Optional[str]:
        for key, value in (workflow.get("inputs", {}) or {}).items():
            if "file" in str(key).lower() or "workbook" in str(key).lower():
                return str(value)
        return None

    @staticmethod
    def _failure_kind(error: str, check_results: List[VerificationResult]) -> str:
        lowered = str(error or "").lower()
        if "timeout" in lowered or "timed out" in lowered:
            return "timeout"
        if "selector" in lowered or "element not found" in lowered:
            return "selector_not_found"
        if check_results and any(not result.passed for result in check_results):
            return "verification_failed"
        return "action_failed"

    @staticmethod
    def _safe_retry(step: dict, action_type: str) -> dict:
        side_effect = str(step.get("side_effect") or "").lower()
        retryable = step.get("retryable")
        if retryable is True:
            return {"status": "yes", "reason": "Step declares retryable=true."}
        if side_effect in {"external_write", "destructive"} or action_type in {
            "api.post",
            "api.put",
            "api.patch",
            "api.delete",
        }:
            return {"status": "no", "reason": "Step may write to an external system."}
        if side_effect in {"none", "local_only", "external_read"} or action_type in {
            "no_op",
            "api.get",
            "browser.goto",
            "browser.get_title",
            "browser.get_text",
            "browser.wait_for",
            "browser.wait_for_url",
            "excel.read",
        }:
            return {"status": "yes", "reason": "Action is read-only or local."}
        return {"status": "unknown", "reason": "No side_effect/retryable metadata declared."}

    @staticmethod
    def _recommendation(failure_kind: Optional[str]) -> str:
        mapping = {
            "missing_secret": "Check configuration/secrets and rerun after the secret exists.",
            "input_data_error": "Fix input data before retrying.",
            "selector_not_found": "Repair selector using the evidence bundle.",
            "ambiguous_selector": "Make the selector more specific.",
            "verification_failed": "Check whether the action succeeded, the target rejected it, or the success check is wrong.",
            "timeout": "Check wait policy, app slowness, or the expected condition.",
            "business_rule_rejected": "Fix record data or target business state before retrying.",
            "unexpected_state": "Inspect current URL/window and screenshot evidence.",
            "auth_failed": "Check credentials, session state, MFA, or account lockout.",
            "target_unavailable": "Check target availability before retrying.",
        }
        return mapping.get(str(failure_kind or ""), "Inspect the evidence bundle before rerunning.")

    @staticmethod
    def _target_system(workflow: dict) -> Optional[str]:
        target_systems = workflow.get("target_systems")
        if isinstance(target_systems, list) and target_systems:
            return ", ".join(str(item) for item in target_systems)
        if isinstance(target_systems, str):
            return target_systems
        system_of_record = workflow.get("system_of_record")
        if system_of_record:
            return str(system_of_record)
        return workflow.get("type")

    async def _record_failure(
        self,
        workflow: dict,
        step: dict,
        step_result: dict,
        started_at: float,
        last_successful_step: str,
    ) -> str:
        if not self.failure._run_dir:
            self.failure.start_run(workflow["id"])
        self._flush_pending_logs()
        evidence = await self._capture_failure_evidence(step=step, step_result=step_result)
        verification_failures = [
            check for check in step_result.get("checks", []) if not check.get("passed")
        ]
        first_failure = verification_failures[0] if verification_failures else {}
        error_message = step_result.get("error") or "Step verification failed"
        classification = classify_failure(
            error_message,
            root_observation=first_failure.get("message") or error_message,
        )
        current_stage = step.get("current_stage") or step["id"]
        report_path = self.failure.generate(
            workflow_id=workflow["id"],
            workflow_name=workflow.get("name", workflow["id"]),
            failed_step_id=step["id"],
            failed_step_description=step.get("description", step["id"]),
            action_type=step.get("action", {}).get("type", "unknown"),
            error_type="WorkflowStepFailed",
            error_message=error_message,
            error_category="unknown",
            last_successful_step=last_successful_step,
            verification_failures=verification_failures,
            evidence=evidence,
            duration_ms=(time.time() - started_at) * 1000,
            repro_command=f"python main.py --run-yaml {self._workflow_path}",
            current_stage=current_stage,
            intended_action=step.get("intent") or step.get("description", step["id"]),
            expected_result=self._redact_optional(first_failure.get("expected")),
            actual_result=self._redact_optional(first_failure.get("actual")),
            input_record_id=step.get("record_id"),
            target_system=self._target_system(workflow),
            retry_attempt=step_result.get("attempts"),
            max_attempts=step_result.get("max_attempts"),
            retry_allowed=bool(classification.get("retry_allowed")),
            side_effect_risk=str(classification.get("side_effect_risk")),
            human_review_required=bool(classification.get("human_review_required")),
            first_failed_stage=current_stage,
            last_known_good_stage=last_successful_step or None,
            escalation_status=str(classification.get("recommended_route") or "notified"),
            error_class=str(step.get("failure_class") or classification.get("error_class")),
            failure_kind=step_result.get("failure_kind"),
        )
        return str(Path(report_path).resolve()) if report_path else ""

    async def _capture_failure_evidence(
        self,
        step: dict | None = None,
        step_result: dict | None = None,
    ) -> Dict[str, Any]:
        evidence: Dict[str, Any] = {}

        browser = self._drivers.get("browser")
        if browser and browser.page:
            try:
                screenshot = await browser.page.screenshot()
                evidence["screenshot"] = self._relative_evidence_path(
                    self.failure.save_screenshot(data=screenshot)
                )
            except Exception as exc:
                evidence["screenshot_error"] = str(exc)
            try:
                raw_dom = await browser.page.content()
                redacted_dom = redact_text(raw_dom, self._secret_values(), max_chars=200000)
                evidence["dom_snapshot"] = self._relative_evidence_path(
                    self.failure.save_artifact("dom_snapshot_redacted.html", redacted_dom)
                )
            except Exception as exc:
                evidence["dom_error"] = str(exc)
            evidence["current_url"] = sanitize_url(browser.page.url)

            if self._console_entries:
                evidence["console_logs"] = self._relative_evidence_path(
                    self.failure.save_artifact("console.jsonl", self._jsonl(self._console_entries))
                )
            if self._network_entries:
                evidence["network_logs"] = self._relative_evidence_path(
                    self.failure.save_artifact("network.jsonl", self._jsonl(self._network_entries))
                )
            if self._needs_selector_repair(step, step_result):
                plan = selector_repair_plan(
                    workflow_path=self._workflow_path,
                    step=step or {},
                    current_url=sanitize_url(browser.page.url),
                )
                evidence["selector_repair"] = self._relative_evidence_path(
                    self.failure.save_artifact(
                        "selector_repair_suggestion.json",
                        json.dumps(plan, indent=2, default=str),
                    )
                )

        if self._last_api_context:
            api_preview = {
                "status_code": self._last_api_context.get("status_code"),
                "headers": self._last_api_context.get("response_headers", {}),
                "body_preview": self._last_api_context.get("body_preview", ""),
                "url": self._last_api_context.get("url", ""),
            }
            evidence["api_response"] = self._relative_evidence_path(
                self.failure.save_artifact("api_response.json", json.dumps(api_preview, indent=2))
            )

        action = step.get("action") if isinstance(step, dict) else {}
        desktop = self._desktop_driver_for_evidence(action if isinstance(action, dict) else {})
        if desktop:
            driver_type = str(getattr(desktop, "driver_type", "windows_ui"))
            backend = "win32" if "win32" in driver_type.lower() else "uia"
            try:
                screenshot_path = Path(await desktop.screenshot(name="desktop_failure.png"))
                if screenshot_path.exists():
                    evidence["desktop_screenshot"] = self._relative_evidence_path(
                        self.failure.save_screenshot(data=screenshot_path.read_bytes())
                    )
                else:
                    evidence["desktop_screenshot"] = self._relative_evidence_path(
                        str(screenshot_path)
                    )
            except Exception as exc:
                evidence["desktop_screenshot_error"] = str(exc)
            try:
                tree = await desktop.dump_tree(max_depth=3)
                tree_key = "win32_tree" if backend == "win32" else "uia_tree"
                evidence[tree_key] = self._relative_evidence_path(
                    self.failure.save_artifact(f"{tree_key}.json", json.dumps(tree, indent=2))
                )
            except Exception as exc:
                evidence[f"{backend}_tree_error"] = str(exc)
            selector_quality, weak_step_reason, verification_method = (
                self._desktop_step_evidence_metadata(step if isinstance(step, dict) else {})
            )
            evidence["desktop"] = {
                "driver": getattr(desktop, "driver_type", "windows_ui"),
                "backend": backend,
                "app_name": getattr(desktop, "_app_name", None),
                "connected": getattr(desktop, "_connected", None),
                "selector_quality": selector_quality,
                "weak_step_reason": weak_step_reason,
                "verification_method": verification_method,
            }

        return evidence

    def _desktop_driver_for_evidence(self, action: dict) -> Any:
        if str(action.get("type", "")).startswith("desktop."):
            backend = self._desktop_backend(action)
            return self._drivers.get(f"desktop:{backend}") or (
                self._drivers.get("desktop") if backend == "uia" else None
            )
        return (
            self._drivers.get("desktop")
            or self._drivers.get("desktop:uia")
            or self._drivers.get("desktop:win32")
        )

    def _desktop_step_evidence_metadata(
        self,
        step: dict,
    ) -> tuple[str | None, str | None, str | None]:
        action = step.get("action") if isinstance(step.get("action"), dict) else {}
        selector = action.get("selector") if isinstance(action.get("selector"), dict) else {}
        try:
            from harness.rpa.schema import _selector_quality

            selector_quality = _selector_quality(action)
        except Exception:
            selector_quality = None
        weak_step_reason = (
            action.get("weak_step_reason")
            or selector.get("weak_step_reason")
            or selector.get("reason")
        )
        if selector_quality in {"weak", "coordinate_fallback"} and not weak_step_reason:
            weak_step_reason = "weak desktop selector fallback requires evidence-backed repair"
        checks = step.get("success_check") or []
        if isinstance(checks, dict):
            checks = [checks]
        verification_types = [
            str(check.get("type"))
            for check in checks
            if isinstance(check, dict) and check.get("type")
        ]
        verification_method = ", ".join(verification_types) if verification_types else None
        return selector_quality, weak_step_reason, verification_method

    async def _close_drivers(self):
        for driver in list(self._drivers.values()):
            try:
                await driver.close()
            except Exception as exc:
                self.logger.warning(f"Driver close failed: {exc}")
        self._drivers.clear()

    def _redact_check_result(self, result: VerificationResult) -> dict:
        return json.loads(
            json.dumps(
                result.to_dict(),
                default=str,
            ),
            object_hook=lambda obj: redact_mapping(obj, self._secret_values(), max_chars=500),
        )

    def _redact_runtime_text(self, value: Any, max_chars: int = 500) -> str:
        return redacted_preview(value, self._secret_values(), max_chars=max_chars)

    def _redact_optional(self, value: Any, max_chars: int = 500) -> Optional[str]:
        if value is None:
            return None
        return self._redact_runtime_text(value, max_chars=max_chars)

    def _checks_passed(self, results: List[VerificationResult]) -> bool:
        return bool(results) and all(result.passed for result in results)

    def _verification_error(self, results: List[VerificationResult]) -> str:
        failures = [result for result in results if not result.passed]
        if not failures:
            return "Action failed before verification"
        return "; ".join(
            result.message or f"{result.check_type.value} failed" for result in failures
        )

    @staticmethod
    def _step_max_attempts(step: dict) -> int:
        attempts = 1
        for recovery in step.get("recovery", []) or []:
            if isinstance(recovery, dict) and recovery.get("type") == "retry":
                attempts = max(attempts, int(recovery.get("max_attempts", 1)))
        return attempts

    @staticmethod
    def _needs_selector_repair(step: dict | None, step_result: dict | None) -> bool:
        if not step or not isinstance(step, dict):
            return False
        action = step.get("action", {})
        if not isinstance(action, dict) or "selector" not in action:
            return False
        result_text = json.dumps(step_result or {}, default=str).lower()
        return "selector" in result_text or "element" in result_text or "not found" in result_text

    def _is_browser_check(self, check_type: CheckType) -> bool:
        return check_type in {
            CheckType.URL_CONTAINS,
            CheckType.URL_EQUALS,
            CheckType.VISIBLE_TEXT,
            CheckType.SELECTOR_VISIBLE,
            CheckType.SELECTOR_HIDDEN,
            CheckType.FIELD_HAS_VALUE,
        }

    def _is_api_check(self, check_type: CheckType) -> bool:
        return check_type in {
            CheckType.STATUS_CODE,
            CheckType.JSON_PATH_EQUALS,
            CheckType.RESPONSE_CONTAINS,
        }

    def _relative_evidence_path(self, path: str) -> str:
        if not path or not self.failure._run_dir:
            return path
        try:
            return str(Path(path).resolve().relative_to(self.failure._run_dir.resolve()))
        except ValueError:
            return path

    def _jsonl(self, entries: List[dict]) -> str:
        return "\n".join(json.dumps(entry, default=str) for entry in entries) + "\n"

    def _log_entry(self, level: str, step: str, message: str, extra: dict = None):
        entry = {"level": level, "step": step, "message": message, "extra": extra or {}}
        self._pending_logs.append(entry)
        if self.failure._run_dir:
            self.failure.log_entry(level, step, message, extra=extra)

    def _flush_pending_logs(self):
        for entry in self._pending_logs:
            self.failure.log_entry(
                entry["level"],
                entry["step"],
                entry["message"],
                extra=entry.get("extra") or None,
            )

    async def _sleep_ms(self, ms: int):
        import asyncio

        await asyncio.sleep(max(ms, 0) / 1000)

    def _optional_int(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        return int(value)

    def _secret_values(self) -> List[str]:
        return [
            secret.reveal() if hasattr(secret, "reveal") else str(secret)
            for secret in self._secrets.values()
        ]
