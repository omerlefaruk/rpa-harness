"""
Memory worker — FastAPI HTTP service on port 38777.
Provides REST API for memory search, observation ingestion, and session management.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from harness.memory.database import MemoryDatabase
from harness.memory.search import MemorySearch
from harness.logger import HarnessLogger


def create_memory_app(db_path: str = "./data/memory.db") -> FastAPI:
    app = FastAPI(title="RPA Memory Worker", version="0.1.0")
    logger = HarnessLogger("memory-server")
    db = MemoryDatabase(db_path, logger=logger)
    search_engine = MemorySearch(memory_db=db)

    @app.get("/health")
    async def health():
        return {"status": "ok", "database": str(db.db_path)}

    @app.post("/memory/observe")
    async def add_observation(
        session_id: str,
        step_id: int,
        step_name: str,
        action: str = "",
        tool_used: str = "",
        tool_args: Optional[Dict] = None,
        success: bool = True,
        error_message: str = "",
        error_category: str = "",
        selector_used: str = "",
        selector_healed: str = "",
        duration_ms: float = 0,
        screenshot_path: str = "",
        output_summary: str = "",
    ):
        obs_id = db.add_observation(
            session_id=session_id,
            step_id=step_id,
            step_name=step_name,
            action=action,
            tool_used=tool_used,
            tool_args=tool_args or {},
            success=success,
            error_message=error_message,
            error_category=error_category,
            selector_used=selector_used,
            selector_healed=selector_healed,
            duration_ms=duration_ms,
            screenshot_path=screenshot_path,
            output_summary=output_summary,
        )
        return {"id": obs_id, "status": "stored"}

    @app.get("/memory/search")
    async def search(
        q: str = Query(..., description="Search query"),
        type: str = Query("all", description="Search type: all, selector, workflow, error"),
        limit: int = Query(10, ge=1, le=50),
    ):
        results = search_engine.search_index(q, search_type=type, limit=limit)
        return {"query": q, "type": type, "count": len(results), "results": results}

    @app.get("/memory/search/ft")
    async def search_fulltext(
        q: str = Query(..., description="Full-text search query"),
        limit: int = Query(10, ge=1, le=50),
    ):
        results = db.search_ft(q, limit=limit)
        return {"query": q, "count": len(results), "results": results}

    @app.get("/memory/context/{obs_id}")
    async def get_context(
        obs_id: int,
        window: int = Query(5, ge=1, le=20),
    ):
        context = search_engine.get_context(obs_id, window=window)
        if not context:
            raise HTTPException(status_code=404, detail="Observation not found")
        return context

    @app.post("/memory/observations")
    async def get_observations(ids: List[int]):
        details = search_engine.get_details(ids)
        return {"count": len(details), "results": details}

    @app.get("/memory/selectors")
    async def get_selectors(
        url: str = Query(..., description="URL pattern to match"),
        limit: int = Query(10, ge=1, le=50),
    ):
        results = db.get_selectors(url, limit=limit)
        return {"url_pattern": url, "count": len(results), "selectors": results}

    @app.get("/memory/sessions")
    async def get_sessions(limit: int = Query(10, ge=1, le=50)):
        sessions = db.get_recent_sessions(limit=limit)
        return {"count": len(sessions), "sessions": sessions}

    @app.get("/memory/session/{session_id}")
    async def get_session(session_id: str):
        context = db.get_session_context(session_id)
        return {"session_id": session_id, "context": context}

    @app.get("/")
    @app.get("/ui")
    async def dashboard():
        sessions = db.get_recent_sessions(limit=20)
        return HTMLResponse(_dashboard_html(sessions))

    return app


def _dashboard_html(sessions: List[Dict[str, Any]]) -> str:
    session_rows = ""
    for s in sessions:
        status_color = {"passed": "#22c55e", "failed": "#ef4444", "running": "#3b82f6"}.get(
            s.get("status", ""), "#6b7280"
        )
        session_rows += f"""
        <tr>
            <td>{s['id'][:12]}</td>
            <td>{s.get('workflow_name', '')[:40]}</td>
            <td style="color:{status_color};font-weight:bold">{s.get('status', '')}</td>
            <td>{s.get('successful_steps', 0)}/{s.get('failed_steps', 0) or 0}</td>
            <td>{s.get('duration_seconds', 0):.1f}s</td>
            <td>{s.get('start_time', '')[:19] if s.get('start_time') else ''}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RPA Memory Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin:0; padding:32px; background:#f3f4f6; }}
        .container {{ max-width:1100px; margin:0 auto; background:white; border-radius:12px; padding:32px; box-shadow:0 4px 6px rgba(0,0,0,0.1); }}
        h1 {{ color:#111827; }}
        table {{ width:100%; border-collapse:collapse; margin-top:16px; }}
        th {{ text-align:left; padding:12px; background:#f9fafb; font-weight:600; }}
        td {{ padding:12px; border-bottom:1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>RPA Memory</h1>
        <table>
            <thead><tr>
                <th>Session</th><th>Workflow</th><th>Status</th>
                <th>Steps</th><th>Duration</th><th>Started</th>
            </tr></thead>
            <tbody>{session_rows}</tbody>
        </table>
    </div>
</body>
</html>"""


def run_memory_server(db_path: str = "./data/memory.db", port: int = 38777):
    import uvicorn
    app = create_memory_app(db_path)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_memory_server()
