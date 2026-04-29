"""
YAML workflow runner.

Loads validated YAML workflows and executes the supported v1 action set against
real browser/API drivers.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from harness.memory.recorder import MemoryRecorder
from harness.reporting.failure_report import FailureReport
from harness.security import (
    redact_mapping,
    redact_text,
    redacted_preview,
    sanitize_url,
)
from harness.verification import CheckType, SuccessCheck, VerificationResult, WorkflowVerifier
from harness.verification.checks import CheckRunner

INPUT_REF_RE = re.compile(r"\$\{inputs\.([A-Za-z_][A-Za-z0-9_]*)\}")
VARIABLE_REF_RE = re.compile(r"\$\{variables\.([A-Za-z_][A-Za-z0-9_]*)\}")
SECRET_REF_RE = re.compile(r"\$\{secrets\.([A-Za-z_][A-Za-z0-9_]*)\}")

SUPPORTED_RUNTIME_PREFIXES = ("browser.", "api.", "desktop.", "excel.")


class YamlWorkflowRunner:
    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig.from_env()
        self.logger = HarnessLogger("yaml-runner")
        self.verifier = WorkflowVerifier()
        self.failure = FailureReport("./runs")
        self.memory = MemoryRecorder.from_harness_config(self.config)
        self._drivers: Dict[str, Any] = {}
        self._inputs: Dict[str, Any] = {}
        self._variables: Dict[str, Any] = {}
        self._secret_env_names: Dict[str, str] = {}
        self._secrets: Dict[str, str] = {}
        self._workflow_path = ""
        self._last_api_context: Optional[Dict[str, Any]] = None
        self._console_entries: List[dict] = []
        self._network_entries: List[dict] = []
        self._pending_logs: List[dict] = []

    def load(self, path: str) -> dict:
        workflow = yaml.safe_load(Path(path).read_text()) or {}
        errors = self.verifier.validate(workflow)
        if errors:
            raise ValueError(f"Workflow validation failed: {'; '.join(errors)}")
        return workflow

    def validate(self, path: str) -> List[str]:
        workflow = yaml.safe_load(Path(path).read_text()) or {}
        return self.verifier.validate(workflow)

    async def run(self, workflow_path: str) -> Dict[str, Any]:
        self._workflow_path = str(workflow_path)
        workflow = self.load(workflow_path)
        workflow_id = workflow["id"]
        workflow_name = workflow.get("name", workflow_id)
        self._last_api_context = None
        self._console_entries = []
        self._network_entries = []
        self._pending_logs = []

        self._inputs = self._resolve_inputs(workflow.get("inputs", {}))
        self._variables = dict(self._inputs)
        self._secret_env_names = self._resolve_secret_env_names(workflow.get("credentials", {}))

        missing_secrets = self._missing_secrets()
        if missing_secrets:
            return {
                "status": "failed",
                "failure_type": "config",
                "reason": "Missing required secrets",
                "missing_secrets": missing_secrets,
                "steps": [],
            }
        self._secrets = self._load_secrets()

        unsupported = self._unsupported_runtime_actions(workflow)
        if unsupported:
            return {
                "status": "failed",
                "failure_type": "unsupported",
                "reason": "Workflow contains actions not supported by YAML execution v1",
                "unsupported_actions": unsupported,
                "steps": [],
            }

        start_time = time.time()
        steps: List[Dict[str, Any]] = []
        memory_session_id = self.memory.new_session_id("yaml")
        last_successful_step = ""
        original_auto_heal = self.config.auto_heal_selectors
        self.config.auto_heal_selectors = False

        self.logger.info(f"Running workflow: {workflow_name} ({len(workflow['steps'])} steps)")
        await self.memory.start_session(
            memory_session_id,
            f"Run YAML workflow {workflow_name}",
            custom_title=workflow_name,
        )

        try:
            for step in workflow.get("steps", []):
                step_result = await self._run_step(step)
                steps.append(step_result)
                await self.memory.record_observation(
                    content_session_id=memory_session_id,
                    tool_name="yaml_step",
                    tool_input={"step": step.get("id"), "action": step.get("action", {})},
                    tool_response=step_result,
                    tool_use_id=f"yaml-step-{step.get('id')}",
                )

                if step_result["status"] == "passed":
                    last_successful_step = step["id"]
                    continue

                report_path = await self._record_failure(
                    workflow=workflow,
                    step=step,
                    step_result=step_result,
                    started_at=start_time,
                    last_successful_step=last_successful_step,
                )
                step_result["failure_report"] = report_path
                await self.memory.summarize(memory_session_id, step_result)
                return {
                    "status": "failed",
                    "failure_type": "execution",
                    "workflow_id": workflow_id,
                    "workflow_name": workflow_name,
                    "step": step["id"],
                    "reason": step_result.get("error") or "Verification failed",
                    "failure_report": report_path,
                    "steps": steps,
                    "duration_ms": (time.time() - start_time) * 1000,
                }

            result = {
                "status": "passed",
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "steps_completed": len(steps),
                "steps": steps,
                "duration_ms": (time.time() - start_time) * 1000,
            }
            await self.memory.summarize(memory_session_id, result)
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
        action_result: Dict[str, Any] = {}
        check_results: List[VerificationResult] = []
        last_error = ""

        self._log_entry("INFO", step_id, f"Starting: {step_desc}")

        async def run_action_and_verify() -> tuple[Dict[str, Any], List[VerificationResult]]:
            nonlocal attempts
            attempts += 1
            result = await self._execute_action(step)
            results = await self._verify_step(step, result)
            return result, results

        try:
            action_result, check_results = await run_action_and_verify()
        except Exception as exc:
            last_error = str(exc)

        if self._checks_passed(check_results):
            return self._step_result(
                step_id, action_type, started_at, attempts, check_results, destructive
            )

        for recovery in step.get("recovery", []) or []:
            recovery_type = recovery.get("type")

            if recovery_type == "retry":
                max_attempts = int(recovery.get("max_attempts", 1))
                while attempts < max_attempts:
                    try:
                        action_result, check_results = await run_action_and_verify()
                        last_error = ""
                    except Exception as exc:
                        last_error = str(exc)
                        check_results = []
                    if self._checks_passed(check_results):
                        return self._step_result(
                            step_id, action_type, started_at, attempts, check_results, destructive
                        )

            elif recovery_type == "wait":
                await self._sleep_ms(int(recovery.get("ms", recovery.get("duration_ms", 1000))))
                should_reexecute = bool(last_error) or action_type.startswith("api.")
                if should_reexecute:
                    try:
                        action_result, check_results = await run_action_and_verify()
                        last_error = ""
                    except Exception as exc:
                        last_error = str(exc)
                        check_results = []
                else:
                    check_results = await self._verify_step(step, action_result)
                if self._checks_passed(check_results):
                    return self._step_result(
                        step_id, action_type, started_at, attempts, check_results, destructive
                    )

            elif recovery_type == "refresh_page":
                browser = self._drivers.get("browser")
                if browser and browser.page:
                    await browser.page.reload(wait_until="load")
                try:
                    action_result, check_results = await run_action_and_verify()
                    last_error = ""
                except Exception as exc:
                    last_error = str(exc)
                    check_results = []
                if self._checks_passed(check_results):
                    return self._step_result(
                        step_id, action_type, started_at, attempts, check_results, destructive
                    )

        result = self._step_result(
            step_id, action_type, started_at, attempts, check_results, destructive
        )
        result["status"] = "failed"
        result["error"] = last_error or self._verification_error(check_results)
        self._log_entry("ERROR", step_id, result["error"])
        return result

    def _step_result(
        self,
        step_id: str,
        action_type: str,
        started_at: float,
        attempts: int,
        check_results: List[VerificationResult],
        destructive: bool,
    ) -> Dict[str, Any]:
        return {
            "step_id": step_id,
            "action_type": action_type,
            "status": "passed" if self._checks_passed(check_results) else "failed",
            "duration_ms": (time.time() - started_at) * 1000,
            "attempts": attempts,
            "checks": [self._redact_check_result(result) for result in check_results],
            "destructive": destructive,
            "error": "",
        }

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
            "response_headers": redact_mapping(dict(response.headers), self._secrets.values()),
            "body_preview": redacted_preview(body, self._secrets.values(), max_chars=4096),
            "url": sanitize_url(str(response.url)),
        }

    async def _execute_desktop_action(self, action_type: str, action: dict) -> Dict[str, Any]:
        driver = await self._get_desktop_driver()
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

        if op == "click":
            selector = self._desktop_selector(action.get("selector", {}))
            element = await driver.find_element(timeout=timeout, **selector)
            if element is None:
                raise RuntimeError(f"Desktop element not found: {selector}")
            await driver.click(timeout=timeout, **selector)
            return {
                "element_exists": True,
                "elements": [element.to_dict()],
                "selector_visible": True,
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
                actual=redacted_preview(body, self._secrets.values(), max_chars=500),
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
                else redacted_preview(value, self._secrets.values(), 100),
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

    async def _get_desktop_driver(self):
        if "desktop" in self._drivers:
            return self._drivers["desktop"]

        import sys

        if not sys.platform.startswith("win"):
            raise RuntimeError(
                "Desktop YAML runtime requires Windows UIAutomation on Windows; "
                f"current platform is {sys.platform}."
            )

        from harness.drivers.windows_ui import WindowsUIDriver

        driver = WindowsUIDriver(config=self.config)
        if not getattr(driver, "_pywinauto", None):
            raise RuntimeError(
                "Desktop YAML runtime requires pywinauto. Install the Windows optional "
                "dependencies before running desktop workflows."
            )
        self._drivers["desktop"] = driver
        return driver

    def _attach_browser_evidence_handlers(self, driver):
        page = driver.page

        def on_console(message):
            try:
                if message.type == "error":
                    self._console_entries.append(
                        {
                            "type": message.type,
                            "text": redacted_preview(message.text, self._secrets.values(), 500),
                        }
                    )
            except Exception:
                pass

        def on_request_failed(request):
            try:
                failure = request.failure or {}
                self._network_entries.append(
                    {
                        "url": sanitize_url(request.url),
                        "method": request.method,
                        "error_text": redact_text(
                            failure.get("errorText", ""), self._secrets.values(), 300
                        ),
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
            return page.locator(f"#{value}")
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

    def _load_secrets(self) -> Dict[str, str]:
        return {
            logical_name: os.environ[env_name]
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

        def replace_input(match):
            return str(self._inputs.get(match.group(1), match.group(0)))

        def replace_variable(match):
            return str(self._variables.get(match.group(1), match.group(0)))

        def replace_secret(match):
            name = match.group(1)
            if name not in self._secrets:
                raise RuntimeError(f"Secret '{name}' is not available")
            return self._secrets[name]

        result = INPUT_REF_RE.sub(replace_input, result)
        result = VARIABLE_REF_RE.sub(replace_variable, result)
        result = SECRET_REF_RE.sub(replace_secret, result)
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

    async def _record_failure(
        self,
        workflow: dict,
        step: dict,
        step_result: dict,
        started_at: float,
        last_successful_step: str,
    ) -> str:
        self.failure.start_run(workflow["id"])
        self._flush_pending_logs()
        evidence = await self._capture_failure_evidence()
        report_path = self.failure.generate(
            workflow_id=workflow["id"],
            workflow_name=workflow.get("name", workflow["id"]),
            failed_step_id=step["id"],
            failed_step_description=step.get("description", step["id"]),
            action_type=step.get("action", {}).get("type", "unknown"),
            error_type="WorkflowStepFailed",
            error_message=step_result.get("error") or "Step verification failed",
            error_category="unknown",
            last_successful_step=last_successful_step,
            verification_failures=[
                check for check in step_result.get("checks", []) if not check.get("passed")
            ],
            evidence=evidence,
            duration_ms=(time.time() - started_at) * 1000,
            repro_command=f"python main.py --run-yaml {self._workflow_path}",
        )
        return str(Path(report_path).resolve()) if report_path else ""

    async def _capture_failure_evidence(self) -> Dict[str, Any]:
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
                evidence["dom_snapshot"] = self._relative_evidence_path(
                    self.failure.save_dom(await browser.page.content())
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

        return evidence

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
            object_hook=lambda obj: redact_mapping(obj, self._secrets.values(), max_chars=500),
        )

    def _checks_passed(self, results: List[VerificationResult]) -> bool:
        return bool(results) and all(result.passed for result in results)

    def _verification_error(self, results: List[VerificationResult]) -> str:
        failures = [result for result in results if not result.passed]
        if not failures:
            return "Action failed before verification"
        return "; ".join(
            result.message or f"{result.check_type.value} failed" for result in failures
        )

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
