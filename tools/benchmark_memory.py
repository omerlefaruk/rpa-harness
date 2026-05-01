#!/usr/bin/env python3
"""
Benchmark RPA Memory store and HTTP service paths.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.memory.server import create_memory_app
from harness.memory.store import MemoryStore


PROJECT = "rpa-harness-benchmark"
SECRET = "fixture-secret-value"


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
class BenchmarkResult:
    name: str
    records: int
    queries: int
    metrics: list[Metric] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def main() -> int:
    args = parse_args()
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now()
    direct = run_store_benchmark(args.records, args.queries)
    service = run_service_benchmark(args.records, args.queries)
    finished = datetime.now()

    report_path = report_dir / f"rpa_memory_benchmark_{started.strftime('%Y%m%d_%H%M%S')}.html"
    report_path.write_text(
        render_html(
            direct=direct,
            service=service,
            started=started,
            finished=finished,
            args=args,
        ),
        encoding="utf-8",
    )

    print(str(report_path))
    return 0 if direct.passed and service.passed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark RPA Memory")
    parser.add_argument("--records", type=int, default=1000, help="Observation records to insert")
    parser.add_argument("--queries", type=int, default=100, help="Search/timeline iterations")
    parser.add_argument("--report-dir", default="./reports", help="HTML report output directory")
    return parser.parse_args()


def run_store_benchmark(records: int, queries: int) -> BenchmarkResult:
    result = BenchmarkResult("SQLite store", records, queries)
    db_path = temp_db_path()
    try:
        store = MemoryStore(db_path)
        try:
            session_ids = [f"store-session-{i}" for i in range(5)]
            observations = build_observations(records)

            result.metrics.append(measure("create_or_update_session", len(session_ids), lambda: [
                store.create_or_update_session(session_id, PROJECT, f"Benchmark session {session_id}")
                for session_id in session_ids
            ]))

            def insert_all() -> None:
                for index, observation in enumerate(observations):
                    store.add_observation(
                        content_session_id=session_ids[index % len(session_ids)],
                        tool_name=observation["tool_name"],
                        tool_input=observation["tool_input"],
                        tool_response=observation["tool_response"],
                        cwd="/tmp/rpa-harness",
                    )

            result.metrics.append(measure("add_observation", records, insert_all))

            search_terms = ["submit", "login", "reservation", "invoice", "selector"]
            result.metrics.append(measure_repeated(
                "search",
                queries,
                lambda i: store.search(
                    query=search_terms[i % len(search_terms)],
                    project=PROJECT,
                    limit=20,
                ),
            ))

            result.metrics.append(measure_repeated(
                "timeline",
                queries,
                lambda i: store.timeline(
                    query=search_terms[i % len(search_terms)],
                    project=PROJECT,
                    depth_before=2,
                    depth_after=2,
                ),
            ))

            ids = [
                item["id"]
                for item in store.search(query="submit", project=PROJECT, limit=25)["results"]["observations"]
            ]
            result.metrics.append(measure_repeated(
                "get_observations",
                queries,
                lambda _i: store.get_observations(ids, project=PROJECT),
            ))

            add_store_checks(result, store, ids)
        finally:
            store.close()
    finally:
        remove_db_files(db_path)
    return result


def run_service_benchmark(records: int, queries: int) -> BenchmarkResult:
    result = BenchmarkResult("FastAPI service", records, queries)
    db_path = temp_db_path()
    try:
        client = TestClient(create_memory_app(db_path))
        session_ids = [f"service-session-{i}" for i in range(5)]
        observations = build_observations(records)

        result.metrics.append(measure("POST /api/sessions/init", len(session_ids), lambda: [
            checked_response(client.post(
                "/api/sessions/init",
                json={
                    "contentSessionId": session_id,
                    "project": PROJECT,
                    "prompt": f"Benchmark session {session_id}",
                },
            ))
            for session_id in session_ids
        ]))

        def insert_all() -> None:
            for index, observation in enumerate(observations):
                checked_response(client.post(
                    "/api/sessions/observations",
                    json={
                        "contentSessionId": session_ids[index % len(session_ids)],
                        "tool_name": observation["tool_name"],
                        "tool_input": observation["tool_input"],
                        "tool_response": observation["tool_response"],
                        "cwd": "/tmp/rpa-harness",
                    },
                ))

        result.metrics.append(measure("POST /api/sessions/observations", records, insert_all))

        search_terms = ["submit", "login", "reservation", "invoice", "selector"]
        result.metrics.append(measure_repeated(
            "GET /api/search",
            queries,
            lambda i: checked_response(client.get(
                "/api/search",
                params={
                    "query": search_terms[i % len(search_terms)],
                    "project": PROJECT,
                    "limit": 20,
                },
            )),
        ))

        result.metrics.append(measure_repeated(
            "GET /api/timeline",
            queries,
            lambda i: checked_response(client.get(
                "/api/timeline",
                params={
                    "query": search_terms[i % len(search_terms)],
                    "project": PROJECT,
                    "depth_before": 2,
                    "depth_after": 2,
                },
            )),
        ))

        search_result = checked_response(client.get(
            "/api/search",
            params={"query": "submit", "project": PROJECT, "limit": 25},
        ))
        ids = [item["id"] for item in search_result["results"]["observations"]]
        result.metrics.append(measure_repeated(
            "POST /api/observations/batch",
            queries,
            lambda _i: checked_response(client.post(
                "/api/observations/batch",
                json={"ids": ids, "project": PROJECT},
            )),
        ))

        add_service_checks(result, client, ids)
    finally:
        remove_db_files(db_path)
    return result


def build_observations(records: int) -> list[dict[str, Any]]:
    terms = ["submit", "login", "reservation", "invoice", "selector"]
    observations = []
    for index in range(records):
        term = terms[index % len(terms)]
        secret_fragment = f" token={SECRET}" if index == 0 else ""
        observations.append({
            "tool_name": f"browser.{term}",
            "tool_input": {
                "selector": f"[data-testid='{term}-{index % 13}']",
                "url": f"https://example.test/{term}/{index}",
                "headers": {"Authorization": f"Bearer {SECRET}"} if index == 0 else {},
            },
            "tool_response": {
                "status": "passed",
                "title": f"{term} observation {index}",
                "message": f"Verified {term} workflow {index}.{secret_fragment}",
            },
        })
    return observations


def add_store_checks(result: BenchmarkResult, store: MemoryStore, ids: list[int]) -> None:
    search_result = store.search(query="submit", project=PROJECT, limit=10)
    timeline = store.timeline(query="submit", project=PROJECT)
    details = store.get_observations(ids, project=PROJECT)
    serialized = json.dumps(details, default=str)
    result.checks.extend([
        Check("search returns observations", bool(search_result["results"]["observations"]), "query=submit"),
        Check("timeline returns observations", bool(timeline["observations"]), "query=submit"),
        Check("batch details return requested records", len(details["observations"]) == len(ids), f"ids={len(ids)}"),
        Check("secrets are redacted", SECRET not in serialized, "detail payload does not contain fixture secret"),
    ])


def add_service_checks(result: BenchmarkResult, client: TestClient, ids: list[int]) -> None:
    search_result = checked_response(client.get(
        "/api/search",
        params={"query": "submit", "project": PROJECT, "limit": 10},
    ))
    timeline = checked_response(client.get(
        "/api/timeline",
        params={"query": "submit", "project": PROJECT},
    ))
    details = checked_response(client.post(
        "/api/observations/batch",
        json={"ids": ids, "project": PROJECT},
    ))
    serialized = json.dumps(details, default=str)
    result.checks.extend([
        Check("search endpoint returns observations", bool(search_result["results"]["observations"]), "query=submit"),
        Check("timeline endpoint returns observations", bool(timeline["observations"]), "query=submit"),
        Check("batch endpoint returns requested records", len(details["observations"]) == len(ids), f"ids={len(ids)}"),
        Check("endpoint payloads redact secrets", SECRET not in serialized, "detail payload does not contain fixture secret"),
    ])


def checked_response(response) -> Any:
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.text


def measure(name: str, count: int, fn: Callable[[], Any]) -> Metric:
    started = time.perf_counter()
    fn()
    total_ms = (time.perf_counter() - started) * 1000
    per_item = total_ms / max(count, 1)
    return Metric(
        name=name,
        count=count,
        total_ms=total_ms,
        mean_ms=per_item,
        p50_ms=per_item,
        p95_ms=per_item,
        p99_ms=per_item,
        ops_per_sec=count / (total_ms / 1000) if total_ms else 0,
    )


def measure_repeated(name: str, count: int, fn: Callable[[int], Any]) -> Metric:
    timings = []
    for index in range(count):
        started = time.perf_counter()
        fn(index)
        timings.append((time.perf_counter() - started) * 1000)
    return metric_from_timings(name, timings)


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
    direct: BenchmarkResult,
    service: BenchmarkResult,
    started: datetime,
    finished: datetime,
    args: argparse.Namespace,
) -> str:
    all_passed = direct.passed and service.passed
    duration = (finished - started).total_seconds()
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>RPA Memory Benchmark</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #111827; background: #f8fafc; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin-top: 32px; font-size: 20px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 24px 0; }}
    .tile {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    .label {{ color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .value {{ font-size: 22px; font-weight: 700; margin-top: 6px; }}
    .pass {{ color: #047857; }}
    .fail {{ color: #b91c1c; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
    th {{ background: #f3f4f6; color: #374151; font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .note {{ color: #4b5563; line-height: 1.5; }}
  </style>
</head>
<body>
<main>
  <h1>RPA Memory Benchmark</h1>
  <p class="note">Benchmarks direct SQLite store calls and the FastAPI service surface used by RPA Memory.</p>

  <section class="summary">
    <div class="tile"><div class="label">Result</div><div class="value {'pass' if all_passed else 'fail'}">{'PASS' if all_passed else 'FAIL'}</div></div>
    <div class="tile"><div class="label">Records</div><div class="value">{args.records}</div></div>
    <div class="tile"><div class="label">Queries</div><div class="value">{args.queries}</div></div>
    <div class="tile"><div class="label">Duration</div><div class="value">{duration:.2f}s</div></div>
  </section>

  <section>
    <h2>Environment</h2>
    <table>
      <tr><th>Field</th><th>Value</th></tr>
      <tr><td>Started</td><td>{escape(started.isoformat(timespec="seconds"))}</td></tr>
      <tr><td>Python</td><td>{escape(platform.python_version())}</td></tr>
      <tr><td>Platform</td><td>{escape(platform.platform())}</td></tr>
      <tr><td>Working Directory</td><td class="mono">{escape(os.getcwd())}</td></tr>
    </table>
  </section>

  {render_result(direct)}
  {render_result(service)}
</main>
</body>
</html>"""


def render_result(result: BenchmarkResult) -> str:
    metrics = "\n".join(render_metric_row(metric) for metric in result.metrics)
    checks = "\n".join(render_check_row(check) for check in result.checks)
    return f"""
  <section>
    <h2>{escape(result.name)}</h2>
    <table>
      <tr>
        <th>Operation</th><th>Count</th><th>Total ms</th><th>Mean ms</th>
        <th>P50 ms</th><th>P95 ms</th><th>P99 ms</th><th>Ops/sec</th>
      </tr>
      {metrics}
    </table>
    <h2>{escape(result.name)} Checks</h2>
    <table>
      <tr><th>Check</th><th>Status</th><th>Detail</th></tr>
      {checks}
    </table>
  </section>
"""


def render_metric_row(metric: Metric) -> str:
    return (
        "<tr>"
        f"<td>{escape(metric.name)}</td>"
        f"<td>{metric.count}</td>"
        f"<td>{metric.total_ms:.2f}</td>"
        f"<td>{metric.mean_ms:.3f}</td>"
        f"<td>{metric.p50_ms:.3f}</td>"
        f"<td>{metric.p95_ms:.3f}</td>"
        f"<td>{metric.p99_ms:.3f}</td>"
        f"<td>{metric.ops_per_sec:.1f}</td>"
        "</tr>"
    )


def render_check_row(check: Check) -> str:
    status = "PASS" if check.passed else "FAIL"
    css = "pass" if check.passed else "fail"
    return (
        "<tr>"
        f"<td>{escape(check.name)}</td>"
        f"<td class=\"{css}\">{status}</td>"
        f"<td>{escape(check.detail)}</td>"
        "</tr>"
    )


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def temp_db_path() -> str:
    handle = tempfile.NamedTemporaryFile(prefix="rpa-memory-bench-", suffix=".db", delete=False)
    path = handle.name
    handle.close()
    return path


def remove_db_files(db_path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        path = db_path + suffix
        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
