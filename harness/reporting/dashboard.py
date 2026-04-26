"""
FastAPI web dashboard for live test/workflow monitoring.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from harness.logger import HarnessLogger


def create_dashboard(
    report_dir: str = "./reports",
    title: str = "RPA Harness Dashboard",
) -> FastAPI:
    app = FastAPI(title=title)

    report_path = Path(report_dir)
    if report_path.exists():
        app.mount("/reports", StaticFiles(directory=str(report_path)), name="reports")

    @app.get("/")
    async def index():
        return HTMLResponse(DASHBOARD_HTML.format(title=title, status=status_html()))

    @app.get("/api/status")
    async def status():
        return {
            "title": title,
            "time": datetime.now().isoformat(),
            "reports_dir": str(report_path),
            "reports_count": len(list(report_path.glob("*.html"))) if report_path.exists() else 0,
        }

    @app.get("/api/reports")
    async def list_reports():
        if not report_path.exists():
            return {"reports": []}
        reports = sorted(
            report_path.glob("*.{html,json}".format("html,json")),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )[:20]
        return {
            "reports": [
                {"name": p.name, "size": p.stat().st_size, "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat()}
                for p in reports
            ]
        }

    return app


DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
        .header {{ background: #1e293b; padding: 24px 40px; border-bottom: 1px solid #334155; }}
        .header h1 {{ font-size: 24px; font-weight: 700; }}
        .header p {{ color: #94a3b8; font-size: 14px; margin-top: 4px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; padding: 32px 40px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #334155; }}
        .card h3 {{ font-size: 14px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }}
        .card .value {{ font-size: 36px; font-weight: 700; }}
        .pass {{ color: #22c55e; }}
        .fail {{ color: #ef4444; }}
        .pending {{ color: #f59e0b; }}
        .content {{ padding: 0 40px 32px; }}
        .section {{ margin-bottom: 24px; }}
        .section h2 {{ font-size: 18px; margin-bottom: 12px; color: #e2e8f0; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
        th {{ text-align: left; padding: 12px 16px; background: #334155; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; }}
        td {{ padding: 12px 16px; border-bottom: 1px solid #334155; font-size: 14px; }}
        tr:hover {{ background: #33415522; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p>AI-powered RPA automation harness</p>
    </div>
    <div class="grid">
        <div class="card">
            <h3>Status</h3>
            <div class="value pending">Ready</div>
        </div>
        <div class="card">
            <h3>Memory Port</h3>
            <div class="value" style="color:#3b82f6;">38777</div>
        </div>
        <div class="card">
            <h3>Workers</h3>
            <div class="value" style="color:#a78bfa;">4</div>
        </div>
        <div class="card">
            <h3>Reports</h3>
            <div class="value" style="color:#e2e8f0;" id="reportCount">–</div>
        </div>
    </div>
    <div class="content">
        <div class="section">
            <h2>Quick Commands</h2>
            <div class="card">
                <pre style="color:#94a3b8;font-size:13px;">
python main.py --discover ./tests --run --report html
python main.py --agent "Login to example.com and verify dashboard"
python main.py --serve --port 8080
python main.py --memory-serve
                </pre>
            </div>
        </div>
    </div>
    <script>
        fetch('/api/reports').then(r=>r.json()).then(d=>{{
            document.getElementById('reportCount').textContent = d.reports.length;
        }});
    </script>
</body>
</html>"""


def status_html() -> str:
    return ""


def run_dashboard(port: int = 8080, report_dir: str = "./reports"):
    import uvicorn
    app = create_dashboard(report_dir=report_dir)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
