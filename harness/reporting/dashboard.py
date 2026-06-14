"""
FastAPI web dashboard for live test/workflow and autoresearch monitoring.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

RUN_ONCE_PROCESS: subprocess.Popen[str] | None = None
RUN_ONCE_STARTED_AT: float | None = None


def create_dashboard(
    report_dir: str = "./reports",
    title: str = "RPA Harness Dashboard",
    root_dir: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title=title)
    root_path = Path(root_dir or Path.cwd()).resolve()
    report_path = root_path / report_dir

    if report_path.exists():
        app.mount("/reports", StaticFiles(directory=str(report_path)), name="reports")

    @app.get("/")
    async def index():
        return HTMLResponse(DASHBOARD_HTML.replace("__TITLE__", title))

    @app.get("/api/status")
    async def status():
        return {
            "title": title,
            "time": datetime.now().isoformat(),
            "reports_dir": str(report_path),
            "reports_count": len(list(report_path.glob("*.html"))) if report_path.exists() else 0,
        }

    @app.get("/api/autoresearch/status")
    async def autoresearch_status():
        return collect_autoresearch_status(root_path, report_path)

    @app.post("/api/autoresearch/run-once")
    async def run_autoresearch_once():
        process = current_run_once_process()
        if process is not None:
            raise HTTPException(status_code=409, detail="A dashboard-started run is already active.")
        started = start_autoresearch_once(root_path)
        return {"started": True, "pid": started.pid, "time": datetime.now().isoformat()}

    @app.get("/api/reports")
    async def list_reports():
        run_path = root_path / "runs"
        run_reports = collect_run_reports(run_path)
        if not report_path.exists():
            return {"reports": [], "runs": run_reports}
        reports = sorted(
            list(report_path.glob("*.html")) + list(report_path.glob("*.json")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:20]
        return {
            "reports": [
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                }
                for p in reports
            ],
            "runs": run_reports,
        }

    return app


def collect_autoresearch_status(root_path: Path, report_path: Path) -> dict[str, Any]:
    session_dir = root_path / ".autoresearch"
    supervisor_entries = read_jsonl_tail(session_dir / "supervisor.jsonl", limit=20)
    run_entries = read_jsonl_tail(session_dir / "autoresearch.jsonl", limit=20)
    worktree_entries = read_jsonl_tail(
        session_dir / "worktrees" / "sovereign" / ".autoresearch" / "autoresearch.jsonl",
        limit=20,
    )
    latest_supervisor = supervisor_entries[-1] if supervisor_entries else {}
    latest_run = (worktree_entries or run_entries or [{}])[-1]
    process = current_run_once_process()
    stdout_log = root_path / "logs" / "autoresearch-run-once.out.log"
    stderr_log = root_path / "logs" / "autoresearch-run-once.err.log"

    return {
        "time": datetime.now().isoformat(),
        "services": {
            "dashboard": {"status": "ok", "port": 8080},
            "memory": memory_health(),
        },
        "run_once": {
            "active": process is not None,
            "pid": process.pid if process else None,
            "started_at": RUN_ONCE_STARTED_AT,
            "duration_seconds": round(time.time() - RUN_ONCE_STARTED_AT, 1)
            if RUN_ONCE_STARTED_AT and process
            else None,
            "stdout_tail": tail_text(stdout_log),
            "stderr_tail": tail_text(stderr_log),
        },
        "supervisor": {
            "latest": latest_supervisor,
            "recent": supervisor_entries[-8:],
            "plan_tail": tail_text(session_dir / "supervisor_plan.md", max_chars=5000),
            "learnings_tail": tail_text(session_dir / "autoresearch.learnings.md", max_chars=3000),
        },
        "autoresearch": {
            "latest": latest_run,
            "recent": (worktree_entries or run_entries)[-8:],
        },
        "git": {
            "status": run_text(["git", "status", "--short", "--branch"], root_path),
            "log": run_text(["git", "log", "--oneline", "--decorate", "-8"], root_path),
            "worktrees": run_text(["git", "worktree", "list"], root_path),
        },
        "reports": {
            "count": len(list(report_path.glob("*.html"))) if report_path.exists() else 0,
            "recent_failures": collect_run_reports(root_path / "runs")[:8],
        },
    }


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
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries.append(
            {
                "run_id": data.get("run_id") or report.parent.name,
                "workflow": data.get("workflow_name"),
                "status": data.get("status"),
                "error_class": data.get("error_class"),
                "current_stage": data.get("current_stage"),
                "failed_step_id": data.get("failed_step_id"),
                "human_review_required": data.get("human_review_required"),
                "report": str(report),
                "html_report": str(report.with_suffix(".html")) if report.with_suffix(".html").exists() else "",
                "modified": datetime.fromtimestamp(report.stat().st_mtime).isoformat(),
            }
        )
    return entries


def start_autoresearch_once(root_path: Path) -> subprocess.Popen[str]:
    global RUN_ONCE_PROCESS, RUN_ONCE_STARTED_AT

    logs_dir = root_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = (logs_dir / "autoresearch-run-once.out.log").open("w", encoding="utf-8")
    stderr_handle = (logs_dir / "autoresearch-run-once.err.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    RUN_ONCE_STARTED_AT = time.time()
    RUN_ONCE_PROCESS = subprocess.Popen(
        [sys.executable, "-u", "main.py", "--self-improve-once"],
        cwd=root_path,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=stdout_handle,
        stderr=stderr_handle,
        env=env,
    )
    return RUN_ONCE_PROCESS


def current_run_once_process() -> subprocess.Popen[str] | None:
    global RUN_ONCE_PROCESS

    if RUN_ONCE_PROCESS is not None and RUN_ONCE_PROCESS.poll() is None:
        return RUN_ONCE_PROCESS
    RUN_ONCE_PROCESS = None
    return None


def read_jsonl_tail(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def tail_text(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


def memory_health() -> dict[str, Any]:
    try:
        with urlopen("http://127.0.0.1:37777/health", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
            return {"status": payload.get("status", "ok"), "detail": payload}
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return {"status": "down", "detail": str(exc)}


def run_text(command: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    return (completed.stdout or completed.stderr or "").strip()


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>__TITLE__</title>
    <style>
        :root {
            color-scheme: dark;
            --bg: #101214;
            --panel: #171a1d;
            --panel-2: #202429;
            --line: #343b43;
            --text: #f0eee9;
            --muted: #a8aca7;
            --green: #7ccf8a;
            --red: #ff7a70;
            --amber: #e6bf5f;
            --blue: #8bb8ff;
            --ink: #050608;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            background:
                linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 44px 44px,
                linear-gradient(180deg, #151719 0%, var(--bg) 38%, #0b0d0e 100%);
            color: var(--text);
            font-family: "Cascadia Code", "IBM Plex Mono", Consolas, monospace;
            letter-spacing: 0;
        }
        header {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 18px;
            align-items: end;
            padding: 28px 32px 18px;
            border-bottom: 1px solid var(--line);
            background: rgba(16,18,20,.88);
            position: sticky;
            top: 0;
            z-index: 3;
            backdrop-filter: blur(10px);
        }
        h1 {
            margin: 0;
            font-size: 28px;
            line-height: 1;
            font-weight: 800;
            text-transform: uppercase;
        }
        .subline { margin-top: 8px; color: var(--muted); font-size: 12px; }
        .actions { display: flex; gap: 10px; align-items: center; }
        button {
            border: 1px solid var(--line);
            background: var(--text);
            color: var(--ink);
            height: 38px;
            padding: 0 14px;
            font: inherit;
            font-weight: 800;
            cursor: pointer;
            border-radius: 4px;
        }
        button.secondary { background: transparent; color: var(--text); }
        button:disabled { opacity: .5; cursor: not-allowed; }
        main {
            display: grid;
            grid-template-columns: 380px minmax(0, 1fr);
            gap: 18px;
            padding: 18px;
        }
        .panel {
            background: rgba(23,26,29,.94);
            border: 1px solid var(--line);
            border-radius: 6px;
            overflow: hidden;
            min-width: 0;
        }
        .panel h2 {
            margin: 0;
            padding: 12px 14px;
            font-size: 12px;
            text-transform: uppercase;
            background: var(--panel-2);
            border-bottom: 1px solid var(--line);
        }
        .stack { display: grid; gap: 18px; }
        .metrics {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            padding: 12px;
        }
        .metric {
            min-height: 86px;
            padding: 12px;
            border: 1px solid var(--line);
            background: #111416;
            border-radius: 4px;
        }
        .label { color: var(--muted); font-size: 11px; text-transform: uppercase; }
        .value { margin-top: 12px; font-size: 22px; font-weight: 900; overflow-wrap: anywhere; }
        .ok { color: var(--green); }
        .bad { color: var(--red); }
        .warn { color: var(--amber); }
        .info { color: var(--blue); }
        .body { padding: 12px 14px; }
        pre {
            margin: 0;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            color: #d6d1c8;
            font-size: 12px;
            line-height: 1.48;
            max-height: 360px;
            overflow: auto;
        }
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        td { border-bottom: 1px solid #2a3036; padding: 9px 10px; vertical-align: top; }
        td:first-child { width: 160px; color: var(--muted); text-transform: uppercase; }
        .timeline { display: grid; gap: 8px; padding: 12px; }
        .event { border: 1px solid var(--line); border-radius: 4px; padding: 10px; background: #111416; }
        .event strong { display: block; margin-bottom: 5px; }
        .event small { color: var(--muted); }
        @media (max-width: 980px) {
            header { grid-template-columns: 1fr; }
            main { grid-template-columns: 1fr; }
            .metrics { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>RPA Harness Control</h1>
            <div class="subline" id="clock">connecting</div>
        </div>
        <div class="actions">
            <button id="runOnce">Run once</button>
            <button class="secondary" id="refresh">Refresh</button>
        </div>
    </header>
    <main>
        <section class="stack">
            <div class="panel">
                <h2>Live State</h2>
                <div class="metrics">
                    <div class="metric"><div class="label">Memory</div><div class="value" id="memory">-</div></div>
                    <div class="metric"><div class="label">Run Once</div><div class="value" id="runState">-</div></div>
                    <div class="metric"><div class="label">Latest Status</div><div class="value" id="latestStatus">-</div></div>
                    <div class="metric"><div class="label">Reports</div><div class="value" id="reports">-</div></div>
                </div>
            </div>
            <div class="panel">
                <h2>Supervisor Latest</h2>
                <div class="body"><table id="latestTable"></table></div>
            </div>
            <div class="panel">
                <h2>Recent Events</h2>
                <div class="timeline" id="events"></div>
            </div>
        </section>
        <section class="stack">
            <div class="panel">
                <h2>Run Log</h2>
                <div class="body"><pre id="runLog"></pre></div>
            </div>
            <div class="panel">
                <h2>Git</h2>
                <div class="body"><pre id="git"></pre></div>
            </div>
            <div class="panel">
                <h2>Plan Tail</h2>
                <div class="body"><pre id="plan"></pre></div>
            </div>
        </section>
    </main>
    <script>
        const $ = (id) => document.getElementById(id);
        const stateClass = (value) => {
            const text = String(value || '').toLowerCase();
            if (text.includes('ok') || text.includes('merged') || text.includes('pushed') || text.includes('committed')) return 'ok';
            if (text.includes('fail') || text.includes('crash') || text.includes('rejected') || text.includes('down')) return 'bad';
            if (text.includes('warn') || text.includes('running') || text.includes('active')) return 'warn';
            return 'info';
        };
        const setValue = (id, value) => {
            const node = $(id);
            node.className = 'value ' + stateClass(value);
            node.textContent = value || '-';
        };
        const row = (name, value) => `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(value || '-')}</td></tr>`;
        const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

        async function refresh() {
            const res = await fetch('/api/autoresearch/status', { cache: 'no-store' });
            const data = await res.json();
            const latest = data.supervisor.latest || {};
            $('clock').textContent = `last update ${data.time}`;
            setValue('memory', data.services.memory.status);
            setValue('runState', data.run_once.active ? `active ${data.run_once.pid}` : 'idle');
            setValue('latestStatus', latest.status || 'none');
            setValue('reports', data.reports.count);
            $('runOnce').disabled = data.run_once.active;
            $('latestTable').innerHTML = [
                row('status', latest.status),
                row('timestamp', latest.timestamp),
                row('branch', latest.branch),
                row('worktree', latest.worktree),
                row('review', latest.require_review === false ? 'disabled' : latest.require_review),
                row('experiment', latest.experiment ? latest.experiment.tail_output || latest.experiment.exit_code : ''),
            ].join('');
            $('events').innerHTML = (data.supervisor.recent || []).slice().reverse().map(item => `
                <div class="event">
                    <strong class="${stateClass(item.status)}">${escapeHtml(item.status || 'unknown')}</strong>
                    <small>${escapeHtml(item.timestamp || '')}</small>
                    <div>${escapeHtml(item.type || 'supervisor')}</div>
                </div>
            `).join('') || '<div class="event"><strong>no events yet</strong></div>';
            $('runLog').textContent = [data.run_once.stdout_tail, data.run_once.stderr_tail].filter(Boolean).join('\n\n');
            $('git').textContent = [data.git.status, data.git.log, data.git.worktrees].filter(Boolean).join('\n\n');
            $('plan').textContent = data.supervisor.plan_tail || data.supervisor.learnings_tail || '';
        }
        async function runOnce() {
            $('runOnce').disabled = true;
            await fetch('/api/autoresearch/run-once', { method: 'POST' });
            await refresh();
        }
        $('runOnce').addEventListener('click', runOnce);
        $('refresh').addEventListener('click', refresh);
        refresh();
        setInterval(refresh, 2000);
    </script>
</body>
</html>"""


def run_dashboard(port: int = 8080, report_dir: str = "./reports"):
    import uvicorn

    app = create_dashboard(report_dir=report_dir)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


async def serve_dashboard(port: int = 8080, report_dir: str = "./reports"):
    import uvicorn

    app = create_dashboard(report_dir=report_dir)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
