"""
Test reporters: HTML (with embedded screenshots) and JSON (machine-readable).
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from harness.security import redact_text, redact_value


class JSONReporter:
    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, results: List[Any], suite_name: str = "Test Suite",
                 metadata: Dict[str, Any] = None) -> str:
        passed = sum(1 for r in results if _get_passed(r))
        failed = sum(1 for r in results if not _get_passed(r) and _get_status(r) != "skipped")
        total_duration = sum(_get_duration(r) for r in results)

        report = {
            "suite_name": suite_name,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / len(results) * 100, 2) if results else 0,
                "total_duration_ms": round(total_duration, 2),
            },
            "metadata": metadata or {},
            "tests": [redact_value(_result_to_dict(r)) for r in results],
        }
        report["metadata"] = redact_value(report["metadata"])

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"report_{timestamp}.json"
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        return str(path)


class HTMLReporter:
    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, results: List[Any], suite_name: str = "Test Suite",
                 metadata: Dict[str, Any] = None) -> str:
        passed = sum(1 for r in results if _get_passed(r))
        failed = sum(1 for r in results if not _get_passed(r) and _get_status(r) != "skipped")
        total_duration = sum(_get_duration(r) for r in results)
        pass_rate = round(passed / len(results) * 100, 2) if results else 0

        rows = ""
        for r in results:
            status = _get_status(r)
            status_color = {
                "passed": "#22c55e",
                "failed": "#ef4444",
                "skipped": "#f59e0b",
                "error": "#dc2626",
            }.get(status, "#6b7280")

            screenshots_html = ""
            screenshots = _get_screenshots(r)
            for s in screenshots:
                name = Path(s).name if s else "screenshot.png"
                screenshots_html += f'<img src="{name}" style="max-width:200px;margin:4px;border:1px solid #ddd;border-radius:4px;"/>'

            name = redact_text(_get_name(r))
            duration = _get_duration(r)
            error = redact_text(_get_error(r))
            logs = redact_value(_get_logs(r))

            error_html = ""
            if error:
                error_html = f'<pre style="background:#fee2e2;padding:8px;border-radius:4px;overflow:auto;max-height:200px;">{error}</pre>'

            logs_html = ""
            if logs:
                logs_html = '<ul style="font-size:12px;margin:0;padding-left:16px;">' + \
                    ''.join(f'<li>{log}</li>' for log in logs) + '</ul>'

            metadata_html = ""
            meta = redact_value(_get_metadata(r))
            if meta and meta.get("review_data"):
                rd = meta["review_data"]
                snippets_html = ""
                for s in rd.get("review_snippets", []):
                    snippets_html += f'<span style="background:#dbeafe;padding:2px 8px;border-radius:4px;margin:2px;">{s}</span> '
                impressions_html = ""
                for imp in rd.get("guest_impressions", []):
                    impressions_html += f'<span style="background:#fef3c7;padding:2px 8px;border-radius:4px;margin:2px;">{imp}</span> '
                review_card = (
                    f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin-bottom:12px;">'
                    f'<h3 style="margin:0 0 8px 0;color:#166534;">{rd.get("hotel", "Hotel")}</h3>'
                    f'<div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;">'
                    f'<div style="font-size:28px;font-weight:bold;color:#166534;">{rd.get("rating","?")}/10</div>'
                    f'<div style="font-size:16px;color:#374151;">{rd.get("rating_label","")}</div>'
                    f'<div style="font-size:16px;color:#6b7280;">{rd.get("review_count","?")} reviews</div>'
                    f'</div>'
                    f'<div style="margin-top:8px;">{snippets_html}</div>'
                )
                if impressions_html:
                    review_card += f'<div style="margin-top:4px;font-size:13px;color:#92400e;"><strong>Guest impressions:</strong> {impressions_html}</div>'
                if meta.get("note"):
                    review_card += f'<div style="margin-top:8px;font-size:12px;color:#ef4444;font-style:italic;">{meta["note"]}</div>'
                review_card += '</div>'
                metadata_html = review_card

            rows += f"""
            <tr style="border-bottom:1px solid #e5e7eb;">
                <td style="padding:12px;">{name}</td>
                <td style="padding:12px;color:{status_color};font-weight:bold;text-transform:uppercase;">{status}</td>
                <td style="padding:12px;">{duration:.0f}ms</td>
                <td style="padding:12px;">{screenshots_html}</td>
                <td style="padding:12px;">{metadata_html}{error_html}{logs_html}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{suite_name} — RPA Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin:0; padding:40px; background:#f3f4f6; }}
        .container {{ max-width:1200px; margin:0 auto; background:white; border-radius:12px; box-shadow:0 4px 6px rgba(0,0,0,0.1); padding:32px; }}
        h1 {{ margin-top:0; color:#111827; }}
        .summary {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin:24px 0; }}
        .stat {{ background:#f9fafb; padding:20px; border-radius:8px; text-align:center; }}
        .stat-value {{ font-size:32px; font-weight:bold; color:#111827; }}
        .stat-label {{ font-size:14px; color:#6b7280; margin-top:4px; }}
        .stat.pass .stat-value {{ color:#22c55e; }}
        .stat.fail .stat-value {{ color:#ef4444; }}
        table {{ width:100%; border-collapse:collapse; margin-top:24px; }}
        th {{ text-align:left; padding:12px; background:#f9fafb; font-weight:600; color:#374151; }}
        .timestamp {{ color:#6b7280; font-size:14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{suite_name}</h1>
        <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <div class="summary">
            <div class="stat"><div class="stat-value">{len(results)}</div><div class="stat-label">Total</div></div>
            <div class="stat pass"><div class="stat-value">{passed}</div><div class="stat-label">Passed</div></div>
            <div class="stat fail"><div class="stat-value">{failed}</div><div class="stat-label">Failed</div></div>
            <div class="stat"><div class="stat-value">{pass_rate}%</div><div class="stat-label">Pass Rate</div></div>
        </div>
        <p><strong>Duration:</strong> {total_duration/1000:.2f}s</p>
        <table>
            <thead><tr><th>Name</th><th>Status</th><th>Duration</th><th>Screenshots</th><th>Details</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
</body>
</html>"""

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"report_{timestamp}.html"
        with open(path, "w") as f:
            f.write(html)

        return str(path)


def _get_passed(result: Any) -> bool:
    if hasattr(result, "passed"):
        return result.passed
    if isinstance(result, dict):
        return result.get("status") in ("passed", "success")
    return False


def _get_status(result: Any) -> str:
    if hasattr(result, "status"):
        s = result.status
        return s.value if hasattr(s, "value") else str(s)
    if isinstance(result, dict):
        return result.get("status", "unknown")
    return "unknown"


def _get_name(result: Any) -> str:
    if hasattr(result, "name"):
        return result.name
    if isinstance(result, dict):
        return result.get("name", result.get("task", "unnamed"))
    return "unnamed"


def _get_duration(result: Any) -> float:
    if hasattr(result, "duration_ms"):
        return result.duration_ms
    if isinstance(result, dict):
        return result.get("duration_ms", result.get("duration_seconds", 0) * 1000)
    return 0


def _get_error(result: Any) -> str:
    if hasattr(result, "error_message"):
        return result.error_message or ""
    if isinstance(result, dict):
        return result.get("error_message", result.get("error", ""))
    return ""


def _get_screenshots(result: Any) -> List[str]:
    if hasattr(result, "screenshots"):
        return result.screenshots or []
    if isinstance(result, dict):
        return result.get("screenshots", [])
    return []


def _get_logs(result: Any) -> List[str]:
    if hasattr(result, "logs"):
        return result.logs or []
    if isinstance(result, dict):
        return result.get("logs", result.get("steps", []))
    return []


def _get_metadata(result: Any) -> dict:
    if hasattr(result, "metadata"):
        return result.metadata or {}
    if isinstance(result, dict):
        return result.get("metadata", {})
    return {}


def _result_to_dict(result: Any) -> dict:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, dict):
        return result
    return {"name": str(result)}
