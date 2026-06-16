"""SQLite index over run artifacts.

Run folders remain the source of truth; this DB is a rebuildable index.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from harness.security import redact_value


SCHEMA_VERSION = 1


def default_db_path() -> Path:
    return Path(os.getenv("RPA_OBSERVABILITY_DB", "runs/observability.db"))


class ObservabilityDB:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or default_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                workflow TEXT,
                schema_version INTEGER,
                status TEXT,
                input_file TEXT,
                started_at TEXT,
                finished_at TEXT,
                duration_ms REAL,
                run_dir TEXT,
                report_path TEXT,
                timeline_path TEXT,
                records_path TEXT,
                preflight_path TEXT,
                redaction_status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                workflow TEXT,
                phase_id TEXT,
                phase_name TEXT,
                status TEXT,
                started_at TEXT,
                finished_at TEXT,
                duration_ms REAL,
                passed_steps INTEGER DEFAULT 0,
                failed_steps INTEGER DEFAULT 0,
                skipped_steps INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                workflow TEXT,
                phase_id TEXT,
                step_id TEXT,
                record_id TEXT,
                action_type TEXT,
                target_type TEXT,
                status TEXT,
                failure_kind TEXT,
                side_effect TEXT,
                retryable INTEGER,
                safe_retry TEXT,
                started_at TEXT,
                finished_at TEXT,
                duration_ms REAL,
                evidence_bundle_path TEXT,
                repair_packet_path TEXT,
                selector_evidence_path TEXT,
                message TEXT
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                workflow TEXT,
                record_id TEXT,
                row_number INTEGER,
                status TEXT,
                failed_step TEXT,
                failure_kind TEXT,
                evidence_bundle_path TEXT,
                retry_count INTEGER,
                external_reference TEXT,
                safe_retry TEXT,
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                event_id INTEGER,
                timestamp TEXT,
                workflow TEXT,
                event TEXT,
                phase_id TEXT,
                step_id TEXT,
                record_id TEXT,
                status TEXT,
                failure_kind TEXT,
                action_type TEXT,
                evidence_bundle_path TEXT,
                message_redacted TEXT,
                raw_event_json_redacted TEXT
            );
            CREATE TABLE IF NOT EXISTS evidence_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                workflow TEXT,
                phase_id TEXT,
                step_id TEXT,
                record_id TEXT,
                failure_kind TEXT,
                evidence_bundle_path TEXT,
                screenshot_path TEXT,
                dom_snapshot_path TEXT,
                uia_snapshot_path TEXT,
                api_preview_path TEXT,
                logs_path TEXT,
                selector_evidence_path TEXT,
                repair_packet_path TEXT,
                redaction_status TEXT
            );
            CREATE TABLE IF NOT EXISTS selector_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                workflow TEXT,
                phase_id TEXT,
                step_id TEXT,
                record_id TEXT,
                failed_selector TEXT,
                strategy TEXT,
                target_type TEXT,
                selector_quality TEXT,
                top_candidate TEXT,
                top_candidate_score REAL,
                selector_evidence_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS repair_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                workflow TEXT,
                phase_id TEXT,
                step_id TEXT,
                record_id TEXT,
                failure_kind TEXT,
                safe_retry TEXT,
                recommended_next_action TEXT,
                repair_packet_path TEXT,
                evidence_bundle_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS builder_sessions (
                session_id TEXT PRIMARY KEY,
                task_name TEXT,
                target_type TEXT,
                status TEXT,
                session_dir TEXT,
                workflow_draft_path TEXT,
                report_path TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_runs_workflow_status_started ON runs(workflow, status, started_at);
            CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id);
            CREATE INDEX IF NOT EXISTS idx_steps_failure ON steps(workflow, failure_kind);
            CREATE INDEX IF NOT EXISTS idx_steps_step_failure ON steps(step_id, failure_kind);
            CREATE INDEX IF NOT EXISTS idx_records_run_record ON records(run_id, record_id);
            CREATE INDEX IF NOT EXISTS idx_timeline_run_time ON timeline_events(run_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_selector_failures_workflow_step ON selector_failures(workflow, step_id);
            CREATE INDEX IF NOT EXISTS idx_evidence_run_phase_step ON evidence_artifacts(run_id, phase_id, step_id);
            CREATE INDEX IF NOT EXISTS idx_repair_packets_run ON repair_packets(run_id);
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        self.conn.commit()

    def replace_run(self, run_dir: Path) -> dict[str, Any]:
        manifest_path = run_dir / "run_manifest.json"
        manifest = _read_json(manifest_path)
        if not manifest:
            return {"status": "skipped", "reason": "run_manifest.json missing or corrupt", "run_dir": str(run_dir)}
        run_id = str(manifest.get("run_id") or run_dir.name)
        workflow = manifest.get("workflow")
        self._delete_run(run_id)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, workflow, schema_version, status, input_file, started_at,
                finished_at, duration_ms, run_dir, report_path, timeline_path,
                records_path, preflight_path, redaction_status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                run_id,
                workflow,
                int(manifest.get("schema_version") or 1),
                manifest.get("status"),
                manifest.get("input_file"),
                manifest.get("started_at"),
                manifest.get("finished_at"),
                manifest.get("duration_ms"),
                str(run_dir.resolve()),
                _join(run_dir, manifest.get("report") or "report.html"),
                _join(run_dir, manifest.get("timeline") or "timeline.jsonl"),
                _join(run_dir, manifest.get("records") or "records.jsonl"),
                _join(run_dir, manifest.get("preflight") or "preflight.json"),
                (manifest.get("redaction") or {}).get("status"),
            ),
        )
        self._index_timeline(run_id, workflow, run_dir)
        self._index_records(run_id, workflow, run_dir)
        self._index_failure_artifacts(run_id, workflow, run_dir)
        self.conn.commit()
        return {"status": "indexed", "run_id": run_id}

    def list_runs(self, workflow: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        where, params = _filters({"workflow": workflow, "status": status})
        return self._rows(f"SELECT * FROM runs{where} ORDER BY started_at DESC LIMIT ? OFFSET ?", [*params, limit, offset])

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_run_timeline(self, run_id: str, after_id: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM timeline_events WHERE run_id = ?"
        params: list[Any] = [run_id]
        if after_id is not None:
            sql += " AND event_id > ?"
            params.append(after_id)
        sql += " ORDER BY event_id, id"
        return self._rows(sql, params)

    def get_run_phases(self, run_id: str) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM phases WHERE run_id = ? ORDER BY id", [run_id])

    def get_run_steps(self, run_id: str) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM steps WHERE run_id = ? ORDER BY id", [run_id])

    def get_run_records(self, run_id: str) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM records WHERE run_id = ? ORDER BY id", [run_id])

    def get_failures(self, workflow: str | None = None, failure_kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where, params = _filters({"workflow": workflow, "failure_kind": failure_kind})
        return self._rows(f"SELECT * FROM steps{where} AND status = 'failed' ORDER BY id DESC LIMIT ?" if where else "SELECT * FROM steps WHERE status = 'failed' ORDER BY id DESC LIMIT ?", [*params, limit])

    def get_failure_kinds_summary(self) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT failure_kind, COUNT(*) AS count
            FROM steps
            WHERE failure_kind IS NOT NULL
            GROUP BY failure_kind
            ORDER BY count DESC, failure_kind
            """,
            [],
        )

    def get_selector_failures(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM selector_failures ORDER BY created_at DESC", [])

    def get_record_failures(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM records WHERE status = 'failed' ORDER BY id DESC", [])

    def get_recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.list_runs(limit=limit)

    def search_events(self, query: str) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT * FROM timeline_events WHERE message_redacted LIKE ? OR raw_event_json_redacted LIKE ? ORDER BY id DESC",
            [f"%{query}%", f"%{query}%"],
        )

    def search_records(self, record_id: str) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM records WHERE record_id = ? ORDER BY id DESC", [record_id])

    def get_workflow_health(self, workflow: str) -> dict[str, Any]:
        rows = self._rows(
            "SELECT status, COUNT(*) AS count FROM runs WHERE workflow = ? GROUP BY status",
            [workflow],
        )
        return {"workflow": workflow, "runs_by_status": rows, "failure_kinds": self.get_failure_kinds_summary()}

    def close(self) -> None:
        self.conn.close()

    def _delete_run(self, run_id: str) -> None:
        for table in (
            "phases",
            "steps",
            "records",
            "timeline_events",
            "evidence_artifacts",
            "selector_failures",
            "repair_packets",
        ):
            self.conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))

    def _index_timeline(self, run_id: str, workflow: str | None, run_dir: Path) -> None:
        phase_status: dict[str, dict[str, Any]] = {}
        for seq, event in enumerate(_read_jsonl(run_dir / "timeline.jsonl"), 1):
            event = redact_value(event)
            event_id = int(event.get("event_id") or seq)
            phase = event.get("phase") or event.get("phase_id")
            if phase:
                state = phase_status.setdefault(str(phase), {"passed": 0, "failed": 0, "skipped": 0, "status": "running"})
                if event.get("event") == "step.passed":
                    state["passed"] += 1
                elif event.get("event") == "step.failed":
                    state["failed"] += 1
                    state["status"] = "failed"
                elif event.get("event") == "phase.passed" and state["status"] != "failed":
                    state["status"] = "passed"
            self.conn.execute(
                """
                INSERT INTO timeline_events (
                    run_id, event_id, timestamp, workflow, event, phase_id, step_id,
                    record_id, status, failure_kind, action_type, evidence_bundle_path,
                    message_redacted, raw_event_json_redacted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_id,
                    event.get("timestamp"),
                    event.get("workflow") or workflow,
                    event.get("event"),
                    phase,
                    event.get("step_id"),
                    event.get("record_id"),
                    event.get("status"),
                    event.get("failure_kind"),
                    event.get("action_type"),
                    _join(run_dir, event.get("evidence_bundle")),
                    event.get("message"),
                    json.dumps(event, default=str),
                ),
            )
            if str(event.get("event", "")).startswith("step."):
                self.conn.execute(
                    """
                    INSERT INTO steps (
                        run_id, workflow, phase_id, step_id, record_id, action_type,
                        target_type, status, failure_kind, duration_ms,
                        evidence_bundle_path, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        event.get("workflow") or workflow,
                        phase,
                        event.get("step_id"),
                        event.get("record_id"),
                        event.get("action_type"),
                        _target_type(event.get("action_type")),
                        event.get("status"),
                        event.get("failure_kind"),
                        event.get("duration_ms"),
                        _join(run_dir, event.get("evidence_bundle")),
                        event.get("message"),
                    ),
                )
        for phase_id, state in phase_status.items():
            self.conn.execute(
                "INSERT INTO phases(run_id, workflow, phase_id, phase_name, status, passed_steps, failed_steps, skipped_steps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, workflow, phase_id, phase_id, state["status"], state["passed"], state["failed"], state["skipped"]),
            )

    def _index_records(self, run_id: str, workflow: str | None, run_dir: Path) -> None:
        for record in _read_jsonl(run_dir / "records.jsonl"):
            record = redact_value(record)
            self.conn.execute(
                """
                INSERT INTO records (
                    run_id, workflow, record_id, row_number, status, failed_step,
                    failure_kind, evidence_bundle_path, retry_count,
                    external_reference, safe_retry, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record.get("workflow") or workflow,
                    record.get("record_id"),
                    record.get("row_number"),
                    record.get("status"),
                    record.get("failed_step"),
                    record.get("failure_kind"),
                    _join(run_dir, record.get("evidence_bundle")),
                    record.get("retry_count"),
                    record.get("external_reference"),
                    json.dumps(record.get("safe_retry"), default=str) if record.get("safe_retry") is not None else None,
                    record.get("timestamp"),
                    record.get("finished_at"),
                ),
            )

    def _index_failure_artifacts(self, run_id: str, workflow: str | None, run_dir: Path) -> None:
        evidence = redact_value(_read_json(run_dir / "evidence_bundle.json"))
        repair = redact_value(_read_json(run_dir / "repair_packet.json"))
        artifacts = evidence.get("artifacts") or {}
        if evidence:
            self.conn.execute(
                """
                INSERT INTO evidence_artifacts (
                    run_id, workflow, phase_id, step_id, record_id, failure_kind,
                    evidence_bundle_path, screenshot_path, dom_snapshot_path,
                    uia_snapshot_path, api_preview_path, logs_path,
                    selector_evidence_path, repair_packet_path, redaction_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    evidence.get("workflow_name") or workflow,
                    evidence.get("phase_id"),
                    evidence.get("step_id"),
                    evidence.get("input_record_id"),
                    evidence.get("failure_kind"),
                    _join(run_dir, "evidence_bundle.json"),
                    _join(run_dir, artifacts.get("screenshot")),
                    _join(run_dir, artifacts.get("dom_snapshot")),
                    _join(run_dir, artifacts.get("uia_snapshot")),
                    _join(run_dir, artifacts.get("api_preview")),
                    _join(run_dir, artifacts.get("logs")),
                    _join(run_dir, artifacts.get("selector_evidence")),
                    _join(run_dir, artifacts.get("repair_packet")),
                    (evidence.get("redaction") or {}).get("status"),
                ),
            )
        if repair:
            self.conn.execute(
                """
                INSERT INTO repair_packets (
                    run_id, workflow, step_id, record_id, failure_kind, safe_retry,
                    recommended_next_action, repair_packet_path, evidence_bundle_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repair.get("workflow_name") or workflow,
                    repair.get("step_id"),
                    repair.get("record_id"),
                    repair.get("failure_kind"),
                    repair.get("safe_retry"),
                    repair.get("recommended_next_action"),
                    _join(run_dir, "repair_packet.json"),
                    _join(run_dir, "evidence_bundle.json"),
                ),
            )

    def _rows(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]


def index_runs(runs_dir: str | Path = "runs", db_path: str | Path | None = None) -> dict[str, Any]:
    runs_dir = Path(runs_dir)
    db = ObservabilityDB(db_path or runs_dir / "observability.db")
    warnings = []
    indexed = 0
    for manifest in sorted(runs_dir.glob("*/run_manifest.json")):
        try:
            result = db.replace_run(manifest.parent)
            if result["status"] == "indexed":
                indexed += 1
            else:
                warnings.append(result)
        except Exception as exc:
            warnings.append({"run_dir": str(manifest.parent), "warning": str(exc)})
    db.close()
    return {"status": "indexed", "indexed_runs": indexed, "warnings": warnings, "db_path": str(db_path or runs_dir / "observability.db")}


def rebuild_runs(runs_dir: str | Path = "runs", db_path: str | Path | None = None) -> dict[str, Any]:
    db_path = Path(db_path or Path(runs_dir) / "observability.db")
    if db_path.exists():
        db_path.unlink()
    return index_runs(runs_dir, db_path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _join(run_dir: Path, value: Any) -> str | None:
    if not value:
        return None
    path = Path(str(value))
    return str(path if path.is_absolute() else (run_dir / path).resolve())


def _target_type(action_type: Any) -> str | None:
    prefix = str(action_type or "").split(".", 1)[0]
    return prefix if prefix in {"browser", "desktop", "api", "excel"} else None


def _filters(values: dict[str, Any]) -> tuple[str, list[Any]]:
    parts = []
    params = []
    for key, value in values.items():
        if value:
            parts.append(f"{key} = ?")
            params.append(value)
    return (" WHERE " + " AND ".join(parts) if parts else ""), params
