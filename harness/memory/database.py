"""
Persistent memory system — adapted from claude-mem patterns.
SQLite + FTS5 for observability, selector caching, and error pattern learning.
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from harness.config import HarnessConfig
from harness.logger import HarnessLogger


class MemoryDatabase:
    def __init__(self, db_path: str, logger: Optional[HarnessLogger] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logger or HarnessLogger("memory-db")
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                workflow_name TEXT NOT NULL,
                task_description TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT,
                total_steps INTEGER DEFAULT 0,
                successful_steps INTEGER DEFAULT 0,
                failed_steps INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0,
                config_snapshot TEXT,
                summary_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                step_id INTEGER,
                step_name TEXT NOT NULL,
                action TEXT,
                tool_used TEXT,
                tool_args TEXT,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                error_category TEXT,
                selector_used TEXT,
                selector_healed TEXT,
                duration_ms REAL DEFAULT 0,
                screenshot_path TEXT,
                output_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
                step_name, action, tool_used, selector_used, error_message, output_summary,
                content='observations', content_rowid='id'
            );

            CREATE TABLE IF NOT EXISTS selector_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_pattern TEXT NOT NULL,
                page_title TEXT,
                selector TEXT NOT NULL,
                selector_type TEXT DEFAULT 'css',
                element_description TEXT,
                element_type TEXT,
                last_validated TIMESTAMP,
                validation_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                UNIQUE(url_pattern, selector)
            );

            CREATE TABLE IF NOT EXISTS error_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_signature TEXT UNIQUE,
                error_message TEXT,
                error_category TEXT,
                recovery_strategy TEXT,
                recovery_success_rate REAL DEFAULT 0,
                occurrence_count INTEGER DEFAULT 1,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                context_type TEXT,
                context_text TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        self._conn.commit()
        self.logger.info(f"Memory database ready: {self.db_path}")

    def insert_triggers(self):
        self._conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
                INSERT INTO observations_fts(rowid, step_name, action, tool_used, selector_used, error_message, output_summary)
                VALUES (new.id, new.step_name, new.action, new.tool_used, new.selector_used, new.error_message, new.output_summary);
            END;

            CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts, rowid, step_name, action, tool_used, selector_used, error_message, output_summary)
                VALUES ('delete', old.id, old.step_name, old.action, old.tool_used, old.selector_used, old.error_message, old.output_summary);
            END;

            CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
                INSERT INTO observations_fts(observations_fts, rowid, step_name, action, tool_used, selector_used, error_message, output_summary)
                VALUES ('delete', old.id, old.step_name, old.action, old.tool_used, old.selector_used, old.error_message, old.output_summary);
                INSERT INTO observations_fts(rowid, step_name, action, tool_used, selector_used, error_message, output_summary)
                VALUES (new.id, new.step_name, new.action, new.tool_used, new.selector_used, new.error_message, new.output_summary);
            END;
        """)
        self._conn.commit()

    def create_session(self, session_id: str, workflow_name: str, task: str = "",
                       config_snapshot: str = "") -> str:
        self._conn.execute(
            """INSERT INTO sessions (id, workflow_name, task_description, start_time, status, config_snapshot)
               VALUES (?, ?, ?, ?, 'running', ?)""",
            (session_id, workflow_name, task, datetime.now().isoformat(), config_snapshot),
        )
        self._conn.commit()
        return session_id

    def end_session(self, session_id: str, status: str, total_steps: int = 0,
                    successful_steps: int = 0, failed_steps: int = 0,
                    duration_seconds: float = 0, summary_text: str = ""):
        self._conn.execute(
            """UPDATE sessions SET end_time = ?, status = ?, total_steps = ?,
               successful_steps = ?, failed_steps = ?, duration_seconds = ?, summary_text = ?
               WHERE id = ?""",
            (datetime.now().isoformat(), status, total_steps, successful_steps,
             failed_steps, duration_seconds, summary_text, session_id),
        )
        self._conn.commit()

    def add_observation(self, session_id: str, step_id: int, step_name: str,
                        action: str = "", tool_used: str = "", tool_args: dict = None,
                        success: bool = True, error_message: str = "",
                        error_category: str = "", selector_used: str = "",
                        selector_healed: str = "", duration_ms: float = 0,
                        screenshot_path: str = "", output_summary: str = "") -> int:
        cursor = self._conn.execute(
            """INSERT INTO observations (session_id, step_id, step_name, action,
               tool_used, tool_args, success, error_message, error_category,
               selector_used, selector_healed, duration_ms, screenshot_path, output_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, step_id, step_name, action, tool_used,
             json.dumps(tool_args) if tool_args else "{}",
             int(success), error_message, error_category,
             selector_used, selector_healed, duration_ms,
             screenshot_path, output_summary),
        )
        self._conn.commit()
        return cursor.lastrowid

    def upsert_selector(self, url_pattern: str, selector: str, selector_type: str = "css",
                        element_description: str = "", element_type: str = "",
                        page_title: str = "", success: bool = True) -> int:
        existing = self._conn.execute(
            "SELECT id, validation_count, success_count FROM selector_cache WHERE url_pattern = ? AND selector = ?",
            (url_pattern, selector),
        ).fetchone()

        if existing:
            self._conn.execute(
                """UPDATE selector_cache SET
                   last_validated = ?, validation_count = validation_count + 1,
                   success_count = success_count + ?, page_title = COALESCE(?, page_title)
                   WHERE id = ?""",
                (datetime.now().isoformat(), 1 if success else 0, page_title, existing[0]),
            )
            self._conn.commit()
            return existing[0]
        else:
            cursor = self._conn.execute(
                """INSERT INTO selector_cache (url_pattern, page_title, selector,
                   selector_type, element_description, element_type, last_validated,
                   validation_count, success_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (url_pattern, page_title, selector, selector_type,
                 element_description, element_type, datetime.now().isoformat(),
                 1 if success else 0),
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_selectors(self, url_pattern: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT selector, selector_type, element_description, element_type,
               success_count, validation_count,
               CAST(success_count AS REAL) / MAX(validation_count, 1) as success_rate
               FROM selector_cache
               WHERE url_pattern LIKE ?
               ORDER BY success_rate DESC, validation_count DESC
               LIMIT ?""",
            (f"%{url_pattern}%", limit),
        ).fetchall()

        return [
            {
                "selector": r[0], "selector_type": r[1],
                "element_description": r[2], "element_type": r[3],
                "success_count": r[4], "validation_count": r[5],
                "success_rate": round(r[6], 2),
            }
            for r in rows
        ]

    def search(self, query: str, search_type: str = "all", limit: int = 10) -> List[Dict[str, Any]]:
        results = []

        if search_type in ("all", "selector"):
            selectors = self._conn.execute(
                """SELECT selector, element_description, element_type,
                   CAST(success_count AS REAL) / MAX(validation_count, 1) as success_rate
                   FROM selector_cache
                   WHERE element_description LIKE ? OR selector LIKE ?
                   ORDER BY success_rate DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            for r in selectors:
                results.append({
                    "type": "selector",
                    "selector": r[0], "description": r[1],
                    "element_type": r[2], "success_rate": round(r[3], 2),
                })

        if search_type in ("all", "workflow", "error"):
            try:
                workflow_rows = self._conn.execute(
                    """SELECT observations_fts.rank, observations.step_name,
                       observations.tool_used, observations.success, observations.error_message
                       FROM observations_fts
                       JOIN observations ON observations_fts.rowid = observations.id
                       WHERE observations_fts MATCH ?
                       ORDER BY rank LIMIT ?""",
                    (query, limit),
                ).fetchall()
                for r in workflow_rows:
                    results.append({
                        "type": "observation",
                        "rank": r[0], "step_name": r[1],
                        "tool_used": r[2], "success": bool(r[3]),
                        "error_message": r[4] or "",
                    })
            except sqlite3.OperationalError:
                pass

        if search_type in ("all", "error"):
            errors = self._conn.execute(
                """SELECT error_signature, error_category, recovery_strategy,
                   recovery_success_rate, occurrence_count
                   FROM error_patterns
                   WHERE error_signature LIKE ? OR error_message LIKE ?
                   ORDER BY occurrence_count DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            for r in errors:
                results.append({
                    "type": "error_pattern",
                    "signature": r[0], "category": r[1],
                    "strategy": r[2], "success_rate": r[3],
                    "occurrence_count": r[4],
                })

        return results

    def search_ft(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            rows = self._conn.execute(
                """SELECT observations_fts.rank, observations.step_name,
                   observations.tool_used, observations.selector_used,
                   observations.success, observations.error_message,
                   observations.duration_ms, observations.created_at
                   FROM observations_fts
                   JOIN observations ON observations_fts.rowid = observations.id
                   WHERE observations_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        return [
            {
                "rank": r[0], "step_name": r[1], "tool_used": r[2],
                "selector_used": r[3], "success": bool(r[4]),
                "error_message": r[5] or "", "duration_ms": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def get_session_context(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT context_type, context_text FROM session_context WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [{"type": r[0], "text": r[1]} for r in rows]

    def add_session_context(self, session_id: str, context_type: str, context_text: str):
        self._conn.execute(
            "INSERT INTO session_context (session_id, context_type, context_text) VALUES (?, ?, ?)",
            (session_id, context_type, context_text),
        )
        self._conn.commit()

    def update_error_pattern(self, error_signature: str, error_message: str,
                             error_category: str, recovery_strategy: str = "",
                             success: bool = False):
        existing = self._conn.execute(
            "SELECT id, occurrence_count FROM error_patterns WHERE error_signature = ?",
            (error_signature,),
        ).fetchone()

        if existing:
            self._conn.execute(
                """UPDATE error_patterns SET
                   occurrence_count = occurrence_count + 1,
                   last_seen = ?,
                   recovery_success_rate = (
                     (recovery_success_rate * (occurrence_count - 1) + ?) / occurrence_count
                   ),
                   recovery_strategy = COALESCE(NULLIF(?, ''), recovery_strategy)
                   WHERE id = ?""",
                (datetime.now().isoformat(), 1.0 if success else 0.0,
                 recovery_strategy, existing[0]),
            )
        else:
            self._conn.execute(
                """INSERT INTO error_patterns (error_signature, error_message,
                   error_category, recovery_strategy, recovery_success_rate)
                   VALUES (?, ?, ?, ?, ?)""",
                (error_signature, error_message, error_category,
                 recovery_strategy, 1.0 if success else 0.0),
            )
        self._conn.commit()

    def get_recent_sessions(self, limit: int = 5) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT id, workflow_name, task_description, start_time, end_time,
               status, successful_steps, failed_steps, duration_seconds
               FROM sessions ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

        return [
            {
                "id": r[0], "workflow_name": r[1], "task_description": r[2],
                "start_time": r[3], "end_time": r[4], "status": r[5],
                "successful_steps": r[6], "failed_steps": r[7],
                "duration_seconds": r[8],
            }
            for r in rows
        ]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
