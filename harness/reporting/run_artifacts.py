"""CLI helpers for inspecting YAML run artifacts."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from harness.core.artifacts import (
    read_json as _read_json,
    read_jsonl as _read_jsonl,
    read_jsonl_tail as _read_jsonl_tail,
    run_dir_for_id as _run_dir_for_id,
)

__all__ = [
    "collect_run_manifests",
    "collect_run_reports",
    "latest_records",
    "live_tail",
    "merge_runs",
    "print_run_logs",
    "print_run_manifest",
    "print_runs_list",
    "read_run_detail",
    "resolve_run_dir",
    "run_report_path",
]


def collect_run_reports(run_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not run_path.exists():
        return []
    reports = sorted(
        run_path.glob("*/failure_report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    entries: list[dict[str, Any]] = []
    for report in reports:
        data = _read_json(report)
        if not data:
            continue
        entries.append(
            {
                "run_id": data.get("run_id") or report.parent.name,
                "workflow": data.get("workflow_name"),
                "status": data.get("status"),
                "failure_kind": data.get("failure_kind"),
                "error_class": data.get("error_class"),
                "current_stage": data.get("current_stage"),
                "failed_step_id": data.get("failed_step_id"),
                "human_review_required": data.get("human_review_required"),
                "report": str(report),
                "html_report": str(report.with_suffix(".html")) if report.with_suffix(".html").exists() else "",
                "evidence_bundle": str(report.parent / "evidence_bundle.json")
                if (report.parent / "evidence_bundle.json").exists()
                else "",
                "repair_packet": str(report.parent / "repair_packet.json")
                if (report.parent / "repair_packet.json").exists()
                else "",
                "modified": datetime.fromtimestamp(report.stat().st_mtime).isoformat(),
            }
        )
    return entries


def collect_run_manifests(run_path: Path, limit: int = 40) -> list[dict[str, Any]]:
    if not run_path.exists():
        return []
    manifests = sorted(
        run_path.glob("*/run_manifest.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    runs = []
    for manifest in manifests:
        data = _read_json(manifest)
        if not data:
            continue
        runs.append(
            {
                "run_id": data.get("run_id") or manifest.parent.name,
                "workflow": data.get("workflow"),
                "status": data.get("status"),
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "duration_ms": data.get("duration_ms"),
                "summary": data.get("summary") or {},
                "report": str(manifest.parent / "report.html"),
                "report_path": str(manifest.parent / "report.html"),
                "run_directory": data.get("run_directory") or str(manifest.parent),
                "manifest": str(manifest),
                "records": str(manifest.parent / "records.jsonl")
                if (manifest.parent / "records.jsonl").exists()
                else "",
                "modified": datetime.fromtimestamp(manifest.stat().st_mtime).isoformat(),
            }
        )
    return runs


def merge_runs(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in [*primary, *secondary]:
        run_id = str(run.get("run_id") or "")
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        runs.append(run)
    return runs


def read_run_detail(run_path: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_dir_for_id(run_path, run_id)
    manifest = run_dir / "run_manifest.json"
    if not manifest.exists():
        return {}
    return {
        "manifest": _read_json(manifest),
        "timeline": _read_jsonl_tail(run_dir / "timeline.jsonl", limit=200),
        "records": _read_jsonl_tail(run_dir / "records.jsonl", limit=200),
        "report_html": str(run_dir / "report.html") if (run_dir / "report.html").exists() else "",
        "failure_report": _read_json(run_dir / "failure_report.json"),
        "repair_packet": _read_json(run_dir / "repair_packet.json"),
    }


def print_runs_list(runs_dir: str = "runs", limit: int = 20):
    rows = collect_run_manifests(Path(runs_dir), limit=limit)
    if not rows:
        print("No runs found.")
        return
    for row in rows:
        summary = row.get("summary") or {}
        print(
            f"{row.get('run_id')}  {row.get('status')}  {row.get('workflow')}  "
            f"steps {summary.get('passed_steps', 0)}/{summary.get('total_steps', 0)}  "
            f"report {row.get('report_path')}"
        )


def resolve_run_dir(run: str, runs_dir: str = "runs") -> Path:
    path = Path(run)
    if not path.exists():
        path = Path(runs_dir) / run
    if path.is_file():
        path = path.parent
    if not path.exists():
        print(f"Run not found: {run}", file=sys.stderr)
        sys.exit(1)
    return path


def print_run_manifest(run: str, runs_dir: str = "runs"):
    path = resolve_run_dir(run, runs_dir=runs_dir)
    manifest = path / "run_manifest.json"
    if not manifest.exists():
        print(f"Run manifest not found: {run}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(_read_json(manifest), indent=2, default=str))


def print_run_logs(
    run: str,
    tail: int | None = None,
    step: str | None = None,
    runs_dir: str = "runs",
):
    path = resolve_run_dir(run, runs_dir=runs_dir) / "logs.jsonl"
    if not path.exists():
        print(f"Run logs not found: {path}", file=sys.stderr)
        sys.exit(1)
    lines = path.read_text(encoding="utf-8").splitlines()
    if step:
        lines = [
            json.dumps(entry, ensure_ascii=False, default=str)
            for entry in _read_jsonl(path)
            if entry.get("step") == step
        ]
    if tail is not None:
        lines = lines[-max(tail, 0):]
    for line in lines:
        try:
            print(json.dumps(json.loads(line), ensure_ascii=False, default=str))
        except json.JSONDecodeError:
            print(line)

def run_report_path(run: str, runs_dir: str = "runs") -> Path:
    path = resolve_run_dir(run, runs_dir=runs_dir) / "report.html"
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


def latest_records(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for record in _read_jsonl(path):
        record_id = str(record.get("record_id") or "")
        if record_id:
            latest[record_id] = record
    return latest
