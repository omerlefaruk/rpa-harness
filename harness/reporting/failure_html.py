"""Render failure_report.json as a compact HTML investigation view."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from harness.core.artifacts import read_required_json


def render_failure_report_html(report_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(report_path)
    report = read_required_json(source)
    destination = Path(output_path) if output_path else source.with_suffix(".html")
    destination.write_text(_html(report, source.parent), encoding="utf-8")
    return destination


def _html(report: dict[str, Any], base_dir: Path) -> str:
    title = f"{report.get('workflow_name', 'Workflow')} failure"
    evidence = report.get("evidence") or {}
    checks = report.get("verification_failures") or []
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_esc(title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #17202a; background: #f6f7f9; }}
    header {{ padding: 24px 28px; background: #1d2733; color: white; }}
    main {{ padding: 20px 28px; display: grid; gap: 18px; }}
    section {{ background: white; border: 1px solid #d8dde6; border-radius: 6px; padding: 16px; }}
    h1, h2 {{ margin: 0 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    td, th {{ text-align: left; border-bottom: 1px solid #e6e9ef; padding: 8px; vertical-align: top; }}
    td:first-child {{ width: 220px; color: #5b6675; font-weight: 700; }}
    code, pre {{ background: #f0f2f5; border-radius: 4px; }}
    pre {{ padding: 12px; overflow: auto; }}
    .bad {{ color: #b42318; font-weight: 700; }}
    .muted {{ color: #667085; }}
    a {{ color: #175cd3; }}
  </style>
</head>
<body>
  <header>
    <h1>{_esc(title)}</h1>
    <div class="muted">run_id={_esc(report.get('run_id'))}</div>
  </header>
  <main>
    <section>
      <h2>Failure Summary</h2>
      <table>{_rows(report, [
        "status", "current_stage", "failed_step_id", "action_type", "intended_action",
        "expected_result", "actual_result", "failure_kind", "error_class", "error_message",
        "retry_attempt", "max_attempts", "side_effect_risk", "human_review_required",
        "target_system", "escalation_status", "repro_command"
      ])}</table>
    </section>
    <section>
      <h2>Verification Failures</h2>
      {_checks(checks)}
    </section>
    <section>
      <h2>Evidence</h2>
      <table>{_evidence_rows(evidence, base_dir)}</table>
    </section>
  </main>
</body>
</html>"""


def _rows(report: dict[str, Any], fields: list[str]) -> str:
    return "".join(f"<tr><td>{_esc(field)}</td><td>{_esc(report.get(field))}</td></tr>" for field in fields)


def _checks(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "<p>No failed verification checks were recorded.</p>"
    rows = "".join(
        "<tr>"
        f"<td>{_esc(item.get('check_type'))}</td>"
        f"<td>{_esc(item.get('expected'))}</td>"
        f"<td>{_esc(item.get('actual'))}</td>"
        f"<td class='bad'>{_esc(item.get('message'))}</td>"
        "</tr>"
        for item in checks
    )
    return f"<table><tr><th>Check</th><th>Expected</th><th>Actual</th><th>Message</th></tr>{rows}</table>"


def _evidence_rows(evidence: dict[str, Any], base_dir: Path) -> str:
    if not evidence:
        return "<tr><td>none</td><td>No evidence captured.</td></tr>"
    rows = []
    for key, value in evidence.items():
        rows.append(f"<tr><td>{_esc(key)}</td><td>{_evidence_value(value, base_dir)}</td></tr>")
    return "".join(rows)


def _evidence_value(value: Any, base_dir: Path) -> str:
    if isinstance(value, str) and value:
        path = base_dir / value
        if path.exists():
            return f"<a href='{_esc(value)}'>{_esc(value)}</a>"
    return f"<code>{_esc(value)}</code>"


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))
