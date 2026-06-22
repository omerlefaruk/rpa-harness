"""File-backed builder, capture, and discovery helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.core.artifacts import read_json
from harness.security import redact_text, redact_value


def safe_session_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


def create_builder_session(
    task_path: str | Path,
    *,
    session_id: str | None = None,
    root_dir: str | Path = ".",
) -> Path:
    task = Path(task_path)
    if not task.exists():
        raise FileNotFoundError(f"Task file not found: {task}")
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_id = safe_session_id(session_id or f"{now}_{task.stem}")
    session_dir = Path(root_dir) / "builder_sessions" / safe_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "task_spec.md").write_text(
        redact_text(task.read_text(encoding="utf-8")),
        encoding="utf-8",
        newline="\n",
    )
    (session_dir / "assumptions.md").write_text(
        "# Assumptions\n\n- Unverified until target discovery runs.\n",
        encoding="utf-8",
        newline="\n",
    )
    (session_dir / "questions.json").write_text("[]\n", encoding="utf-8", newline="\n")
    write_json(
        session_dir / "discovery_session.json",
        {
            "schema_version": 1,
            "session_id": safe_id,
            "task_file": str(task),
            "status": "created",
            "created_at": now_iso(),
            "artifacts": ["task_spec.md", "assumptions.md", "questions.json"],
        },
    )
    (session_dir / "workflow_draft_report.md").write_text(
        "# Workflow Draft Report\n\nStatus: discovery not run.\n",
        encoding="utf-8",
        newline="\n",
    )
    (session_dir / "unresolved_risks.md").write_text(
        "# Unresolved Risks\n\n- Selectors, success checks, and risky actions are not validated yet.\n",
        encoding="utf-8",
        newline="\n",
    )
    return session_dir.resolve()


def list_builder_sessions(root_dir: str | Path = ".") -> list[dict[str, Any]]:
    base = Path(root_dir) / "builder_sessions"
    if not base.exists():
        return []
    sessions = []
    for session in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not session.is_dir() or session.name.startswith("_"):
            continue
        discovery = read_json(session / "discovery_session.json")
        sessions.append(
            {
                "session_id": session.name,
                "path": str(session),
                "status": discovery.get("status", "unknown"),
                "created_at": discovery.get("created_at"),
                "modified": datetime.fromtimestamp(session.stat().st_mtime).isoformat(),
            }
        )
    return sessions


def read_builder_session(session_id: str, root_dir: str | Path = ".") -> dict[str, Any]:
    session_dir = Path(root_dir) / "builder_sessions" / safe_session_id(session_id)
    if not session_dir.exists():
        raise FileNotFoundError(f"Builder session not found: {session_id}")
    return {
        "session_id": session_dir.name,
        "path": str(session_dir),
        "discovery": read_json(session_dir / "discovery_session.json"),
        "questions": read_json(session_dir / "questions.json", default=[]),
        "task_spec": read_text(session_dir / "task_spec.md"),
        "workflow_draft_report": read_text(session_dir / "workflow_draft_report.md"),
        "unresolved_risks": read_text(session_dir / "unresolved_risks.md"),
        "captures": sorted(path.name for path in session_dir.glob("capture_*")),
    }


def capture_desktop_session(
    *,
    app: str,
    session_dir: str | Path,
    note: str = "",
) -> Path:
    session_path = Path(session_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    capture_dir = session_path / f"capture_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    capture_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "target": app,
        "status": "blocked",
        "created_at": now_iso(),
        "note": redact_text(note),
        "problem": (
            "No interactive desktop recorder is running in this process. "
            "Use UIA dump tools or demonstrate the flow with explicit events."
        ),
        "next_actions": [
            "Run tools/dump_uia_tree.py against the target window.",
            "Provide keyboard/menu shortcuts for risky actions.",
            "Attach screenshots or OCR evidence before using image/coordinate steps.",
        ],
        "events": [],
    }
    write_json(capture_dir / "capture_session.json", payload)
    (capture_dir / "candidate_steps.yaml").write_text(
        "# No candidate steps recorded yet.\n",
        encoding="utf-8",
        newline="\n",
    )
    (capture_dir / "weak_points.md").write_text(
        "# Weak Points\n\n- Discovery is blocked until UIA/Win32/screenshot evidence exists.\n",
        encoding="utf-8",
        newline="\n",
    )
    return capture_dir.resolve()


def validate_discovery_fixtures(root_dir: str | Path = ".") -> dict[str, Any]:
    root = Path(root_dir)
    browser_fixture = root / "workflows" / "capabilities" / "local_browser_form.html"
    desktop_tools = [
        root / "tools" / "dump_uia_tree.py",
        root / ".agents" / "skills" / "windows-ui-automation" / "scripts" / "dump_uia_tree.py",
    ]
    result = {
        "schema_version": 1,
        "status": "passed" if browser_fixture.exists() and any(p.exists() for p in desktop_tools) else "blocked",
        "browser_fixture": {
            "status": "passed" if browser_fixture.exists() else "blocked",
            "artifact": str(browser_fixture),
            "reason": "Local browser fixture exists." if browser_fixture.exists() else "No local browser fixture found.",
        },
        "desktop_fixture": {
            "status": "blocked",
            "tools": [str(path) for path in desktop_tools if path.exists()],
            "reason": "Desktop discovery requires a real target window; fixture validation only proves tooling exists.",
        },
        "validated_at": now_iso(),
    }
    return redact_value(result)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(redact_value(payload), indent=2, default=str), encoding="utf-8", newline="\n")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
