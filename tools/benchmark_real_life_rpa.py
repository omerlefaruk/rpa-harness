#!/usr/bin/env python3
"""
Benchmark real-life-like RPA flows through the YAML runner.

The scenarios are deterministic and local:
- Browser form workflow using Playwright against a generated HTML page.
- API read/write workflow against a local HTTP server.
- Excel write/append/read workflow against a generated workbook.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import platform
import statistics
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.config import HarnessConfig
from harness.memory.client import MemoryClient
from harness.memory.config import MemoryConfig
from harness.rpa.yaml_runner import YamlWorkflowRunner
from harness.security import redact_text


API_SECRET = "real-rpa-api-secret-token"
BROWSER_SECRET = "real-rpa-browser-secret-password"
PROJECT = "rpa-harness"


@dataclass
class Metric:
    name: str
    count: int
    total_ms: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    ops_per_sec: float


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class ScenarioRun:
    status: str
    duration_ms: float
    steps_completed: int
    failed_step: str = ""
    reason: str = ""


@dataclass
class ScenarioResult:
    name: str
    description: str
    iterations: int
    runs: list[ScenarioRun] = field(default_factory=list)
    step_metrics: list[Metric] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(run.status == "passed" for run in self.runs) and all(
            check.passed for check in self.checks
        )

    @property
    def run_metric(self) -> Metric:
        return metric_from_timings(
            f"{self.name} total workflow runtime",
            [run.duration_ms for run in self.runs],
        )


def main() -> int:
    args = parse_args()
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now()
    result = asyncio.run(run_benchmark(args))
    finished = datetime.now()

    report_path = report_dir / f"real_life_rpa_benchmark_{started.strftime('%Y%m%d_%H%M%S')}.html"
    report_path.write_text(
        render_html(result, started, finished, args),
        encoding="utf-8",
    )
    print(str(report_path))
    return 0 if result["passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark real-life-like RPA workflows")
    parser.add_argument("--iterations", type=int, default=3, help="Runs per scenario")
    parser.add_argument("--report-dir", default="./reports", help="HTML report output directory")
    parser.add_argument("--memory-url", default="http://127.0.0.1:37777", help="RPA Memory service URL")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless")
    return parser.parse_args()


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    os.environ["REAL_RPA_API_TOKEN"] = API_SECRET
    os.environ["REAL_RPA_BROWSER_PASSWORD"] = BROWSER_SECRET

    with tempfile.TemporaryDirectory(prefix="real-rpa-bench-") as tmp:
        tmp_path = Path(tmp)
        config = HarnessConfig(
            headless=args.headless,
            enable_vision=False,
            report_dir=str(tmp_path / "reports"),
            screenshot_dir=str(tmp_path / "screenshots"),
            memory=MemoryConfig(
                enabled=True,
                worker_url=args.memory_url,
                required=True,
                project=PROJECT,
                request_timeout_seconds=2,
            ),
        )

        memory_checks = await check_memory_available(args.memory_url)
        api_server = LocalApiServer()
        api_server.start()
        try:
            scenarios = [
                await run_scenario(
                    name="Browser Form Intake",
                    description=(
                        "Real Playwright workflow: open local form, read text, fill fields, "
                        "handle password input, toggle UI, submit, and verify success state."
                    ),
                    iterations=args.iterations,
                    workflow_factory=lambda index: write_browser_workflow(tmp_path, index),
                    config=config,
                ),
                await run_scenario(
                    name="API Customer Payment",
                    description=(
                        "Real HTTP workflow: read customer, read invoice list, post a payment quote, "
                        "and verify status/json/body checks against a local service."
                    ),
                    iterations=args.iterations,
                    workflow_factory=lambda index: write_api_workflow(tmp_path, index, api_server.base_url),
                    config=config,
                ),
                await run_scenario(
                    name="Excel Results Processing",
                    description=(
                        "Excel workflow: create workbook, append processed result row, read it back, "
                        "and verify workbook/sheet/cell checks."
                    ),
                    iterations=args.iterations,
                    workflow_factory=lambda index: write_excel_workflow(tmp_path, index),
                    config=config,
                ),
            ]
        finally:
            api_server.stop()

        memory_checks.extend(await check_memory_observations(args.memory_url, scenarios))
        passed = all(scenario.passed for scenario in scenarios) and all(
            check.passed for check in memory_checks
        )
        return {
            "passed": passed,
            "scenarios": scenarios,
            "memory_checks": memory_checks,
            "api_requests": api_server.requests,
        }


async def run_scenario(
    name: str,
    description: str,
    iterations: int,
    workflow_factory: Callable[[int], Path],
    config: HarnessConfig,
) -> ScenarioResult:
    scenario = ScenarioResult(name=name, description=description, iterations=iterations)
    step_timings: dict[str, list[float]] = {}

    for index in range(iterations):
        workflow_path = workflow_factory(index)
        result = await YamlWorkflowRunner(config).run(str(workflow_path))
        steps = result.get("steps", [])
        duration_ms = float(result.get("duration_ms") or sum(
            float(step.get("duration_ms") or 0) for step in steps
        ))
        scenario.runs.append(
            ScenarioRun(
                status=str(result.get("status")),
                duration_ms=duration_ms,
                steps_completed=int(result.get("steps_completed") or len(steps)),
                failed_step=str(result.get("step") or ""),
                reason=str(result.get("reason") or ""),
            )
        )
        for step in steps:
            key = f"{step.get('action_type', 'unknown')}:{step.get('step_id', 'unknown')}"
            step_timings.setdefault(key, []).append(float(step.get("duration_ms") or 0))

    scenario.step_metrics = [
        metric_from_timings(step_name, timings)
        for step_name, timings in sorted(step_timings.items())
    ]
    scenario.checks.extend([
        Check(
            "all iterations passed",
            all(run.status == "passed" for run in scenario.runs),
            f"{sum(1 for run in scenario.runs if run.status == 'passed')}/{iterations} passed",
        ),
        Check(
            "every run completed steps",
            all(run.steps_completed > 0 for run in scenario.runs),
            f"min steps={min((run.steps_completed for run in scenario.runs), default=0)}",
        ),
    ])
    return scenario


def write_browser_workflow(tmp_path: Path, index: int) -> Path:
    page = tmp_path / f"browser_form_{index}.html"
    page.write_text(browser_fixture_html(), encoding="utf-8")
    workflow = {
        "id": f"real_browser_form_{index}",
        "name": f"Real Browser Form {index}",
        "version": "1.0",
        "type": "browser",
        "inputs": {"target_url": page.as_uri()},
        "credentials": {"form_password": "REAL_RPA_BROWSER_PASSWORD"},
        "steps": [
            {
                "id": "open_form",
                "action": {"type": "browser.goto", "url": "${inputs.target_url}"},
                "success_check": [
                    {"type": "url_contains", "value": page.name},
                    {"type": "selector_visible", "selector": {"strategy": "data-testid", "value": "heading"}},
                ],
            },
            {
                "id": "read_heading",
                "action": {
                    "type": "browser.get_text",
                    "selector": {"strategy": "data-testid", "value": "heading"},
                    "output": "heading_text",
                },
                "success_check": [
                    {"type": "variable_equals", "value": {"var": "heading_text", "value": "Customer Intake"}},
                ],
            },
            {
                "id": "fill_customer",
                "action": {
                    "type": "browser.fill",
                    "selector": {"strategy": "label", "value": "Customer"},
                    "value": f"Customer {index}",
                },
                "success_check": [
                    {"type": "field_has_value", "selector": {"strategy": "label", "value": "Customer"}},
                ],
            },
            {
                "id": "fill_password",
                "action": {
                    "type": "browser.fill",
                    "selector": {"strategy": "label", "value": "Password"},
                    "value": "${secrets.form_password}",
                },
                "success_check": [
                    {
                        "type": "field_has_value",
                        "selector": {"strategy": "label", "value": "Password"},
                        "redacted": True,
                    },
                ],
            },
            {
                "id": "select_priority",
                "action": {
                    "type": "browser.select_option",
                    "selector": {"strategy": "label", "value": "Priority"},
                    "value": "high",
                },
                "success_check": [
                    {"type": "field_has_value", "selector": {"strategy": "label", "value": "Priority"}},
                ],
            },
            {
                "id": "enable_review",
                "action": {"type": "browser.check", "selector": {"strategy": "id", "value": "review"}},
                "success_check": [
                    {"type": "selector_visible", "selector": {"strategy": "data-testid", "value": "review-panel"}},
                ],
            },
            {
                "id": "submit_form",
                "action": {
                    "type": "browser.click",
                    "selector": {"strategy": "role", "role": "button", "name": "Submit"},
                },
                "success_check": [
                    {"type": "visible_text", "value": "Submitted"},
                    {"type": "url_contains", "value": "#submitted"},
                ],
            },
        ],
    }
    return write_yaml(tmp_path, workflow)


def browser_fixture_html() -> str:
    return """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Customer Intake Fixture</title></head>
<body>
  <h1 data-testid="heading">Customer Intake</h1>
  <label for="customer">Customer</label>
  <input id="customer" name="customer" type="text">
  <label for="password">Password</label>
  <input id="password" name="password" type="password">
  <label for="priority">Priority</label>
  <select id="priority" name="priority">
    <option value="">Choose</option>
    <option value="normal">Normal</option>
    <option value="high">High</option>
  </select>
  <label><input id="review" type="checkbox"> Needs review</label>
  <section data-testid="review-panel" hidden>Review required</section>
  <button type="button">Submit</button>
  <p data-testid="success" hidden>Submitted</p>
  <script>
    document.querySelector("#review").addEventListener("change", (event) => {
      document.querySelector("[data-testid='review-panel']").hidden = !event.target.checked;
    });
    document.querySelector("button").addEventListener("click", () => {
      document.querySelector("[data-testid='success']").hidden = false;
      window.location.hash = "submitted";
    });
  </script>
</body>
</html>
"""


def write_api_workflow(tmp_path: Path, index: int, base_url: str) -> Path:
    workflow = {
        "id": f"real_api_customer_payment_{index}",
        "name": f"Real API Customer Payment {index}",
        "version": "1.0",
        "type": "api",
        "allow_destructive": True,
        "credentials": {"api_token": "REAL_RPA_API_TOKEN"},
        "steps": [
            {
                "id": "read_customer",
                "action": {
                    "type": "api.get",
                    "url": f"{base_url}/customers/7",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [
                    {"type": "status_code", "value": 200},
                    {"type": "json_path_equals", "value": {"path": "$.id", "value": "7"}},
                    {"type": "response_contains", "value": "Ada Lovelace"},
                ],
            },
            {
                "id": "read_invoices",
                "action": {
                    "type": "api.get",
                    "url": f"{base_url}/invoices",
                    "params": {"customer_id": "7"},
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                },
                "success_check": [
                    {"type": "status_code", "value": 200},
                    {"type": "json_path_equals", "value": {"path": "$.items[0].status", "value": "open"}},
                    {"type": "response_contains", "value": "INV-100"},
                ],
            },
            {
                "id": "quote_payment",
                "action": {
                    "type": "api.post",
                    "url": f"{base_url}/payments/quote",
                    "headers": {"Authorization": "Bearer ${secrets.api_token}"},
                    "json_data": {"customer_id": "7", "invoice": "INV-100", "amount": 42.5},
                },
                "success_check": [
                    {"type": "status_code", "value": 201},
                    {"type": "json_path_equals", "value": {"path": "$.approved", "value": True}},
                    {"type": "response_contains", "value": "quote-ready"},
                ],
            },
        ],
    }
    return write_yaml(tmp_path, workflow)


def write_excel_workflow(tmp_path: Path, index: int) -> Path:
    workbook = tmp_path / f"results_{index}.xlsx"
    workflow = {
        "id": f"real_excel_results_{index}",
        "name": f"Real Excel Results {index}",
        "version": "1.0",
        "type": "excel",
        "inputs": {"workbook": str(workbook)},
        "steps": [
            {
                "id": "write_headers_and_first_row",
                "action": {
                    "type": "excel.write",
                    "path": "${inputs.workbook}",
                    "sheet": "Results",
                    "headers": ["Customer", "Status", "Amount"],
                    "rows": [[f"Customer {index}", "MATCH", 42.5]],
                },
                "success_check": [
                    {"type": "workbook_exists", "value": "${inputs.workbook}"},
                    {"type": "sheet_exists", "value": "Results"},
                    {"type": "cell_equals", "value": {"sheet": "Results", "cell": "B2", "value": "MATCH"}},
                ],
            },
            {
                "id": "append_audit_row",
                "action": {
                    "type": "excel.append_row",
                    "path": "${inputs.workbook}",
                    "sheet": "Results",
                    "row_data": ["Audit", "DONE", 0],
                },
                "success_check": [
                    {"type": "cell_equals", "value": {"sheet": "Results", "cell": "B3", "value": "DONE"}},
                ],
            },
            {
                "id": "read_results",
                "action": {
                    "type": "excel.read",
                    "path": "${inputs.workbook}",
                    "sheet": "Results",
                    "output": "excel_rows",
                },
                "success_check": [
                    {"type": "variable_has_value", "value": "excel_rows"},
                    {"type": "cell_equals", "value": {"sheet": "Results", "cell": "A3", "value": "Audit"}},
                ],
            },
        ],
    }
    return write_yaml(tmp_path, workflow)


def write_yaml(tmp_path: Path, workflow: dict[str, Any]) -> Path:
    path = tmp_path / f"{workflow['id']}.yaml"
    path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return path


async def check_memory_available(memory_url: str) -> list[Check]:
    client = MemoryClient(MemoryConfig(worker_url=memory_url, required=False))
    result = await client.health()
    return [
        Check(
            "RPA Memory service reachable",
            isinstance(result, dict) and result.get("status") == "ok",
            json.dumps(result, sort_keys=True),
        )
    ]


async def check_memory_observations(
    memory_url: str,
    scenarios: list[ScenarioResult],
) -> list[Check]:
    client = MemoryClient(MemoryConfig(worker_url=memory_url, required=False))
    checks: list[Check] = []
    for scenario in scenarios:
        query = scenario.name.split()[0].lower()
        result = await client.search(query=query, project=PROJECT, type="observations", limit=20)
        observations = result.get("results", {}).get("observations", []) if isinstance(result, dict) else []
        checks.append(
            Check(
                f"memory observations exist for {scenario.name}",
                bool(observations),
                f"query={query}, count={len(observations)}",
            )
        )

    redaction_result = await client.search(query="real-rpa", project=PROJECT, type="observations", limit=50)
    ids = [
        item["id"]
        for item in redaction_result.get("results", {}).get("observations", [])
        if "id" in item
    ][:20]
    details = await client.get_observations(ids=ids, project=PROJECT) if ids else {"observations": []}
    serialized = json.dumps(details, default=str)
    checks.append(
        Check(
            "memory redacts benchmark secrets",
            API_SECRET not in serialized and BROWSER_SECRET not in serialized,
            "detail payload checked for fixture API/browser secrets",
        )
    )
    return checks


class LocalApiServer:
    def __init__(self):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread: threading.Thread | None = None
        self.requests: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args: Any) -> None:
                return None

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                outer.requests.append({
                    "method": "GET",
                    "path": parsed.path,
                    "query": parse_qs(parsed.query),
                    "authorization": self.headers.get("Authorization", ""),
                })
                if parsed.path == "/customers/7":
                    self._json(200, {"id": "7", "name": "Ada Lovelace", "tier": "enterprise"})
                    return
                if parsed.path == "/invoices":
                    self._json(200, {"items": [{"id": "INV-100", "status": "open", "amount": 42.5}]})
                    return
                self._json(404, {"error": "not found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length).decode("utf-8") if length else "{}"
                outer.requests.append({
                    "method": "POST",
                    "path": parsed.path,
                    "body": redact_text(body, [API_SECRET], max_chars=500),
                    "authorization": self.headers.get("Authorization", ""),
                })
                if parsed.path == "/payments/quote":
                    self._json(201, {"approved": True, "message": "quote-ready", "echo": API_SECRET})
                    return
                self._json(404, {"error": "not found"})

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Set-Cookie", f"session={API_SECRET}")
                self.end_headers()
                self.wfile.write(body)

        return Handler


def metric_from_timings(name: str, timings: list[float]) -> Metric:
    total_ms = sum(timings)
    ordered = sorted(timings)
    return Metric(
        name=name,
        count=len(timings),
        total_ms=total_ms,
        mean_ms=statistics.fmean(timings) if timings else 0,
        p50_ms=percentile(ordered, 0.50),
        p95_ms=percentile(ordered, 0.95),
        p99_ms=percentile(ordered, 0.99),
        ops_per_sec=len(timings) / (total_ms / 1000) if total_ms else 0,
    )


def percentile(ordered: list[float], ratio: float) -> float:
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def render_html(
    result: dict[str, Any],
    started: datetime,
    finished: datetime,
    args: argparse.Namespace,
) -> str:
    scenarios: list[ScenarioResult] = result["scenarios"]
    total_runs = sum(len(scenario.runs) for scenario in scenarios)
    total_steps = sum(run.steps_completed for scenario in scenarios for run in scenario.runs)
    duration = (finished - started).total_seconds()
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Real-Life RPA Benchmark Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f7f8fa; color: #172033; }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 32px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin: 30px 0 12px; font-size: 20px; }}
    h3 {{ margin: 22px 0 10px; font-size: 16px; }}
    .note {{ color: #536173; line-height: 1.5; }}
    .summary {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 24px 0; }}
    .tile {{ background: #fff; border: 1px solid #dfe4ea; border-radius: 8px; padding: 16px; }}
    .label {{ color: #677386; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 22px; font-weight: 700; margin-top: 6px; }}
    .pass {{ color: #047857; font-weight: 700; }}
    .fail {{ color: #b91c1c; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dfe4ea; border-radius: 8px; overflow: hidden; margin-bottom: 14px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #e7ebf0; font-size: 13px; vertical-align: top; }}
    th {{ background: #eef2f6; color: #344154; font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  </style>
</head>
<body>
<main>
  <h1>Real-Life RPA Benchmark Report</h1>
  <p class="note">Runs deterministic local workflows through the real YAML runner: browser form automation, HTTP API automation, Excel processing, verification checks, and RPA Memory capture.</p>

  <section class="summary">
    <div class="tile"><div class="label">Result</div><div class="value {'pass' if result['passed'] else 'fail'}">{'PASS' if result['passed'] else 'FAIL'}</div></div>
    <div class="tile"><div class="label">Scenarios</div><div class="value">{len(scenarios)}</div></div>
    <div class="tile"><div class="label">Runs</div><div class="value">{total_runs}</div></div>
    <div class="tile"><div class="label">Steps</div><div class="value">{total_steps}</div></div>
    <div class="tile"><div class="label">Duration</div><div class="value">{duration:.2f}s</div></div>
  </section>

  <section>
    <h2>Environment</h2>
    <table>
      <tr><th>Field</th><th>Value</th></tr>
      <tr><td>Started</td><td>{escape(started.isoformat(timespec="seconds"))}</td></tr>
      <tr><td>Finished</td><td>{escape(finished.isoformat(timespec="seconds"))}</td></tr>
      <tr><td>Python</td><td>{escape(platform.python_version())}</td></tr>
      <tr><td>Platform</td><td>{escape(platform.platform())}</td></tr>
      <tr><td>Memory URL</td><td class="mono">{escape(args.memory_url)}</td></tr>
      <tr><td>Working Directory</td><td class="mono">{escape(os.getcwd())}</td></tr>
    </table>
  </section>

  {''.join(render_scenario(scenario) for scenario in scenarios)}
  {render_checks("RPA Memory Checks", result["memory_checks"])}
</main>
</body>
</html>"""


def render_scenario(scenario: ScenarioResult) -> str:
    return f"""
  <section>
    <h2>{escape(scenario.name)}</h2>
    <p class="note">{escape(scenario.description)}</p>
    <h3>Workflow Runtime</h3>
    <table>
      <tr><th>Operation</th><th>Count</th><th>Total ms</th><th>Mean ms</th><th>P50 ms</th><th>P95 ms</th><th>P99 ms</th><th>Ops/sec</th></tr>
      {render_metric_row(scenario.run_metric)}
    </table>
    <h3>Step Metrics</h3>
    <table>
      <tr><th>Step</th><th>Count</th><th>Total ms</th><th>Mean ms</th><th>P50 ms</th><th>P95 ms</th><th>P99 ms</th><th>Ops/sec</th></tr>
      {''.join(render_metric_row(metric) for metric in scenario.step_metrics)}
    </table>
    {render_runs(scenario.runs)}
    {render_checks(f"{scenario.name} Checks", scenario.checks)}
  </section>
"""


def render_runs(runs: list[ScenarioRun]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{index + 1}</td>"
        f"<td class=\"{'pass' if run.status == 'passed' else 'fail'}\">{escape(run.status)}</td>"
        f"<td>{run.duration_ms:.2f}</td>"
        f"<td>{run.steps_completed}</td>"
        f"<td>{escape(run.failed_step)}</td>"
        f"<td>{escape(run.reason)}</td>"
        "</tr>"
        for index, run in enumerate(runs)
    )
    return f"""
    <h3>Runs</h3>
    <table>
      <tr><th>#</th><th>Status</th><th>Duration ms</th><th>Steps</th><th>Failed Step</th><th>Reason</th></tr>
      {rows}
    </table>
"""


def render_checks(title: str, checks: list[Check]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(check.name)}</td>"
        f"<td class=\"{'pass' if check.passed else 'fail'}\">{'PASS' if check.passed else 'FAIL'}</td>"
        f"<td>{escape(check.detail)}</td>"
        "</tr>"
        for check in checks
    )
    return f"""
    <h3>{escape(title)}</h3>
    <table>
      <tr><th>Check</th><th>Status</th><th>Detail</th></tr>
      {rows}
    </table>
"""


def render_metric_row(metric: Metric) -> str:
    return (
        "<tr>"
        f"<td>{escape(metric.name)}</td>"
        f"<td>{metric.count}</td>"
        f"<td>{metric.total_ms:.2f}</td>"
        f"<td>{metric.mean_ms:.2f}</td>"
        f"<td>{metric.p50_ms:.2f}</td>"
        f"<td>{metric.p95_ms:.2f}</td>"
        f"<td>{metric.p99_ms:.2f}</td>"
        f"<td>{metric.ops_per_sec:.2f}</td>"
        "</tr>"
    )


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
