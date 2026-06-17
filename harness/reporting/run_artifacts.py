"""CLI helpers for inspecting YAML run artifacts."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from harness.config import HarnessConfig


def print_runs_list(runs_dir: str = "runs", limit: int = 20):
    root = Path(runs_dir)
    rows = []
    for manifest in sorted(root.glob("*/run_manifest.json"), reverse=True):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(data)
        if len(rows) >= limit:
            break
    if not rows:
        print("No runs found.")
        return
    for row in rows:
        summary = row.get("summary") or {}
        print(
            f"{row.get('run_id')}  {row.get('status')}  {row.get('workflow')}  "
            f"steps {summary.get('passed_steps', 0)}/{summary.get('total_steps', 0)}  "
            f"report {row.get('run_directory')}/report.html"
        )


def resolve_run_dir(run: str) -> Path:
    path = Path(run)
    if not path.exists():
        path = Path("runs") / run
    if path.is_file():
        path = path.parent
    if not path.exists():
        print(f"Run not found: {run}", file=sys.stderr)
        sys.exit(1)
    return path


def print_run_manifest(run: str):
    path = resolve_run_dir(run)
    manifest = path / "run_manifest.json"
    if not manifest.exists():
        print(f"Run manifest not found: {run}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(json.loads(manifest.read_text(encoding="utf-8")), indent=2, default=str))


def print_run_logs(run: str, tail: int | None = None, step: str | None = None):
    path = resolve_run_dir(run) / "logs.jsonl"
    if not path.exists():
        print(f"Run logs not found: {path}", file=sys.stderr)
        sys.exit(1)
    lines = path.read_text(encoding="utf-8").splitlines()
    if step:
        lines = [
            line for line in lines
            if _jsonl_step(line) == step
        ]
    if tail is not None:
        lines = lines[-max(tail, 0):]
    for line in lines:
        try:
            print(json.dumps(json.loads(line), ensure_ascii=False, default=str))
        except json.JSONDecodeError:
            print(line)


def _jsonl_step(line: str) -> str | None:
    try:
        return json.loads(line).get("step")
    except json.JSONDecodeError:
        return None


def run_report_path(run: str) -> Path:
    path = resolve_run_dir(run) / "report.html"
    if not path.exists():
        print(f"Run report not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.resolve()


def live_tail(run: str, runs_dir: str = "runs"):
    run_dir = resolve_run_dir(run) if Path(run).exists() else Path(runs_dir) / run
    timeline = run_dir / "timeline.jsonl"
    if not timeline.exists():
        print(f"Timeline not found: {timeline}", file=sys.stderr)
        sys.exit(1)
    seen = 0
    while True:
        lines = timeline.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[seen:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            print(json.dumps(event, default=str))
            if event.get("event") == "run.finished":
                return
        seen = len(lines)
        time.sleep(0.5)


async def retry_run(
    run: str,
    *,
    failed_records: bool = False,
    config: HarnessConfig | None = None,
) -> dict:
    from harness.rpa.yaml_runner import YamlWorkflowRunner

    run_dir = resolve_run_dir(run)
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return {"status": "blocked", "reason": "run_manifest.json not found", "run_dir": str(run_dir)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workflow_path = manifest.get("workflow_path")
    if not workflow_path:
        return {"status": "blocked", "reason": "manifest does not include workflow_path", "run_dir": str(run_dir)}
    if not failed_records:
        return {"status": "blocked", "reason": "Only --failed-records retry is supported safely."}
    records = latest_records(run_dir / "records.jsonl")
    failed = [
        record for record in records.values()
        if record.get("status") == "failed" and (record.get("safe_retry") or {}).get("status") == "yes"
    ]
    if not failed:
        return {"status": "blocked", "reason": "No safe failed records to retry.", "run_dir": str(run_dir)}
    results = []
    runner = YamlWorkflowRunner(config or HarnessConfig.from_env())
    for record in failed:
        results.append(await runner.run(workflow_path, only_record=str(record.get("record_id"))))
    return {
        "status": "passed" if all(item.get("status") == "passed" for item in results) else "failed",
        "retried_records": [record.get("record_id") for record in failed],
        "results": results,
    }


def latest_records(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    if not path.exists():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_id = str(record.get("record_id") or "")
        if record_id:
            latest[record_id] = record
    return latest
