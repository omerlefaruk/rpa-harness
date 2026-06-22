"""FastAPI web dashboard for live test/workflow monitoring."""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from harness.builder import list_builder_sessions, read_builder_session
from harness.copilot_session import list_copilot_sessions, read_copilot_session
from harness.observability import ObservabilityDB, index_runs
from harness.reporting.run_artifacts import (
    collect_run_manifests,
    collect_run_reports,
    merge_runs,
    read_jsonl_tail,
    read_run_detail,
    run_dir_for_id,
)
from harness.security import redact_value


def create_dashboard(
    report_dir: str = "./reports",
    title: str = "RPA Harness Dashboard",
    root_dir: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title=title)
    root_path = Path(root_dir or Path.cwd()).resolve()
    report_path = root_path / report_dir
    frontend_dist = root_path / "frontend" / "dist"

    if report_path.exists():
        app.mount("/reports", StaticFiles(directory=str(report_path)), name="reports")
    if frontend_dist.exists():
        app.mount("/app", StaticFiles(directory=str(frontend_dist), html=True), name="app")

    @app.get("/")
    async def index():
        return HTMLResponse(DASHBOARD_HTML.replace("__TITLE__", title))

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "observability_db": str(_observability_db_path(root_path))}

    @app.get("/api/status")
    async def status():
        return {
            "title": title,
            "time": datetime.now().isoformat(),
            "reports_dir": str(report_path),
            "reports_count": len(list(report_path.glob("*.html"))) if report_path.exists() else 0,
            "git": {
                "status": run_text(["git", "status", "--short", "--branch"], root_path),
                "log": run_text(["git", "log", "--oneline", "--decorate", "-8"], root_path),
            },
        }

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

    @app.get("/api/runs")
    async def list_runs():
        manifest_runs = collect_run_manifests(root_path / "runs")
        db_runs = _query_or_empty(root_path, lambda db: db.list_runs(limit=100))
        return {"runs": merge_runs(manifest_runs, db_runs)}

    @app.get("/api/failures")
    async def list_failures():
        return {"failures": _query_or_empty(root_path, lambda db: db.get_failures())}

    @app.get("/api/records")
    async def list_records(record_id: str | None = None):
        if record_id:
            rows = _query_or_empty(root_path, lambda db: db.search_records(record_id))
        else:
            rows = _query_or_empty(root_path, lambda db: db.get_record_failures())
        return {"records": rows}

    @app.get("/api/selector-failures")
    async def selector_failures():
        return {"selector_failures": _query_or_empty(root_path, lambda db: db.get_selector_failures())}

    @app.get("/api/desktop/evidence")
    async def desktop_evidence(run_id: str | None = None):
        return {"evidence": _query_or_empty(root_path, lambda db: db.get_desktop_evidence(run_id=run_id))}

    @app.get("/api/desktop/evidence/{evidence_id}")
    async def desktop_evidence_item(evidence_id: int):
        db_path = _observability_db_path(root_path)
        if not db_path.exists():
            index_runs(root_path / "runs", db_path)
        db = ObservabilityDB(db_path)
        try:
            item = db.get_desktop_evidence_item(evidence_id)
        finally:
            db.close()
        if not item:
            raise HTTPException(status_code=404, detail="desktop evidence not found")
        return item

    @app.get("/api/repair-packets")
    async def repair_packets():
        db = ObservabilityDB(_observability_db_path(root_path))
        try:
            rows = db._rows("SELECT * FROM repair_packets ORDER BY created_at DESC", [])
        finally:
            db.close()
        return {"repair_packets": rows}

    @app.get("/api/observability/summary")
    async def observability_summary():
        db_path = _observability_db_path(root_path)
        if not db_path.exists():
            index_runs(root_path / "runs", db_path)
        db = ObservabilityDB(db_path)
        try:
            return {
                "runs": db.get_recent_runs(limit=10),
                "failure_kinds": db.get_failure_kinds_summary(),
                "record_failures": db.get_record_failures(),
            }
        finally:
            db.close()

    @app.get("/api/runs/{run_id}")
    async def show_run(run_id: str):
        run = read_run_detail(root_path / "runs", run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.get("/api/runs/{run_id}/timeline")
    async def run_timeline(run_id: str, after_id: int | None = None):
        run_dir = run_dir_for_id(root_path / "runs", run_id)
        events = []
        if run_dir.exists():
            events = _timeline_events_from_file(run_dir / "timeline.jsonl", after_id=after_id)
        if not events:
            events = _query_or_empty(root_path, lambda db: db.get_run_timeline(run_id, after_id=after_id))
        if not events and not run_dir.exists():
            raise HTTPException(status_code=404, detail="run not found")
        return {"events": events}

    @app.get("/api/runs/{run_id}/phases")
    async def run_phases(run_id: str):
        return {"phases": _query_or_empty(root_path, lambda db: db.get_run_phases(run_id))}

    @app.get("/api/runs/{run_id}/steps")
    async def run_steps(run_id: str):
        return {"steps": _query_or_empty(root_path, lambda db: db.get_run_steps(run_id))}

    @app.get("/api/runs/{run_id}/records")
    async def run_records(run_id: str):
        return {"records": _query_or_empty(root_path, lambda db: db.get_run_records(run_id))}

    @app.get("/api/runs/{run_id}/failures")
    async def run_failures(run_id: str):
        rows = _query_or_empty(
            root_path,
            lambda db: [
                item for item in db.get_run_steps(run_id)
                if item.get("status") == "failed" or item.get("failure_kind")
            ],
        )
        return {"failures": rows}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, after_id: int | None = None, stream: bool = False):
        run_dir = run_dir_for_id(root_path / "runs", run_id)
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail="run not found")
        if not stream:
            events = _timeline_events_from_file(run_dir / "timeline.jsonl", after_id=after_id)
            return {"events": events}
        return StreamingResponse(
            _sse_timeline(run_dir / "timeline.jsonl", after_id=after_id),
            media_type="text/event-stream",
        )

    @app.get("/api/artifacts")
    async def artifact(run_id: str, path: str):
        run_dir = run_dir_for_id(root_path / "runs", run_id)
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail="run not found")
        target = _safe_artifact_path(run_dir, path)
        if not target:
            raise HTTPException(status_code=403, detail="artifact path is not allowed")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        if target.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            return FileResponse(target)
        text = target.read_text(encoding="utf-8", errors="replace")
        redacted = redact_value(text)
        if target.suffix.lower() == ".json":
            try:
                return JSONResponse(json.loads(redacted))
            except json.JSONDecodeError:
                pass
        return PlainTextResponse(str(redacted))

    @app.get("/api/workflows/{workflow_path:path}/graph")
    async def workflow_graph(workflow_path: str):
        from harness.rpa.schema import generate_workflow_graph
        import yaml

        path = _safe_workspace_path(root_path, workflow_path)
        if not path or not path.exists():
            raise HTTPException(status_code=404, detail="workflow not found")
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return generate_workflow_graph(workflow)

    @app.get("/api/builder/sessions")
    async def builder_sessions():
        return {"sessions": list_builder_sessions(root_path)}

    @app.get("/api/builder/sessions/{session_id}")
    async def builder_session(session_id: str):
        try:
            return read_builder_session(session_id, root_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="builder session not found") from None

    @app.get("/api/copilot/sessions")
    async def copilot_sessions():
        return {"sessions": list_copilot_sessions(root_path)}

    @app.get("/api/copilot/sessions/{session_id}")
    async def copilot_session(session_id: str):
        try:
            return read_copilot_session(session_id, root_dir=root_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="copilot session not found") from None

    return app


def _observability_db_path(root_path: Path) -> Path:
    return root_path / "runs" / "observability.db"


def _query_or_empty(root_path: Path, fn) -> list[dict[str, Any]]:
    db_path = _observability_db_path(root_path)
    if not db_path.exists():
        index_runs(root_path / "runs", db_path)
    db = ObservabilityDB(db_path)
    try:
        return fn(db)
    finally:
        db.close()


def _safe_artifact_path(run_dir: Path, path: str) -> Path | None:
    root = run_dir.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _safe_workspace_path(root_path: Path, path: str) -> Path | None:
    root = root_path.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _timeline_events_from_file(path: Path, after_id: int | None = None) -> list[dict[str, Any]]:
    events = []
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1) if path.exists() else []:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event = redact_value(event)
        event_id = int(event.get("event_id") or index)
        event["event_id"] = event_id
        if after_id is not None and event_id <= after_id:
            continue
        events.append(event)
    return events


async def _sse_timeline(path: Path, after_id: int | None = None):
    sent = after_id or 0
    while True:
        events = _timeline_events_from_file(path, after_id=sent)
        for event in events:
            sent = int(event["event_id"])
            yield f"event: timeline\ndata: {json.dumps(event, default=str)}\n\n"
        if path.exists():
            finished = any(event.get("event") == "run.finished" for event in events)
            if finished:
                return
        await asyncio.sleep(0.5)


def tail_text(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


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
            <button class="secondary" id="refresh">Refresh</button>
        </div>
    </header>
    <main>
        <section class="stack">
            <div class="panel">
                <h2>Live State</h2>
                <div class="metrics">
                    <div class="metric"><div class="label">Reports</div><div class="value" id="reports">-</div></div>
                </div>
            </div>
            <div class="panel">
                <h2>Builder Sessions</h2>
                <div class="timeline" id="builders"></div>
            </div>
        </section>
        <section class="stack">
            <div class="panel">
                <h2>YAML Runs</h2>
                <div class="timeline" id="yamlRuns"></div>
            </div>
            <div class="panel">
                <h2>Git</h2>
                <div class="body"><pre id="git"></pre></div>
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
            const res = await fetch('/api/status', { cache: 'no-store' });
            const data = await res.json();
            $('clock').textContent = `last update ${data.time}`;
            setValue('reports', data.reports_count);
            const runs = await (await fetch('/api/runs', { cache: 'no-store' })).json();
            $('yamlRuns').innerHTML = (runs.runs || []).slice(0, 8).map(run => `
                <div class="event">
                    <strong class="${stateClass(run.status)}">${escapeHtml(run.run_id)}</strong>
                    <small>${escapeHtml(run.workflow || '')} · ${escapeHtml(run.status || '')}</small>
                    <div>steps ${escapeHtml((run.summary || {}).passed_steps || 0)}/${escapeHtml((run.summary || {}).total_steps || 0)} · records ${escapeHtml((run.summary || {}).passed_records || 0)}/${escapeHtml((run.summary || {}).total_records || 0)}</div>
                </div>
            `).join('') || '<div class="event"><strong>no YAML runs yet</strong></div>';
            const builders = await (await fetch('/api/builder/sessions', { cache: 'no-store' })).json();
            $('builders').innerHTML = (builders.sessions || []).slice(0, 6).map(session => `
                <div class="event">
                    <strong class="${stateClass(session.status)}">${escapeHtml(session.session_id)}</strong>
                    <small>${escapeHtml(session.status || '')}</small>
                    <div>${escapeHtml(session.path || '')}</div>
                </div>
            `).join('') || '<div class="event"><strong>no builder sessions yet</strong></div>';
            $('git').textContent = [data.git.status, data.git.log].filter(Boolean).join('\n\n');
        }
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
