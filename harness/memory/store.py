"""
SQLite store for RPA Memory.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from harness.security import redact_mapping, redact_text, redact_value


def _now() -> tuple[str, int]:
    current = datetime.now()
    return current.isoformat(), int(current.timestamp() * 1000)


def _json(value: Any) -> str:
    return json.dumps(redact_value(value), default=str)


class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sdk_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_session_id TEXT UNIQUE NOT NULL,
                memory_session_id TEXT UNIQUE,
                project TEXT NOT NULL,
                platform_source TEXT NOT NULL DEFAULT 'rpa-harness',
                user_prompt TEXT,
                started_at TEXT NOT NULL,
                started_at_epoch INTEGER NOT NULL,
                completed_at TEXT,
                completed_at_epoch INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                prompt_counter INTEGER DEFAULT 0,
                custom_title TEXT
            );

            CREATE TABLE IF NOT EXISTS user_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_session_id TEXT NOT NULL,
                project TEXT NOT NULL,
                prompt_number INTEGER NOT NULL,
                prompt_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_at_epoch INTEGER NOT NULL,
                FOREIGN KEY(content_session_id) REFERENCES sdk_sessions(content_session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                project TEXT NOT NULL,
                text TEXT,
                type TEXT NOT NULL,
                title TEXT,
                subtitle TEXT,
                facts TEXT,
                narrative TEXT,
                concepts TEXT,
                files_read TEXT,
                files_modified TEXT,
                prompt_number INTEGER,
                discovery_tokens INTEGER DEFAULT 0,
                content_hash TEXT,
                agent_type TEXT,
                agent_id TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                created_at_epoch INTEGER NOT NULL,
                FOREIGN KEY(memory_session_id) REFERENCES sdk_sessions(memory_session_id)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                UNIQUE(memory_session_id, content_hash)
            );

            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                project TEXT NOT NULL,
                request TEXT,
                investigated TEXT,
                learned TEXT,
                completed TEXT,
                next_steps TEXT,
                files_read TEXT,
                files_edited TEXT,
                notes TEXT,
                prompt_number INTEGER,
                discovery_tokens INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                created_at_epoch INTEGER NOT NULL,
                FOREIGN KEY(memory_session_id) REFERENCES sdk_sessions(memory_session_id)
                    ON DELETE CASCADE ON UPDATE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_project ON sdk_sessions(project);
            CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project);
            CREATE INDEX IF NOT EXISTS idx_observations_type ON observations(type);
            CREATE INDEX IF NOT EXISTS idx_observations_created ON observations(created_at_epoch DESC);
            CREATE INDEX IF NOT EXISTS idx_summaries_project ON session_summaries(project);
            CREATE INDEX IF NOT EXISTS idx_prompts_project ON user_prompts(project);
            """
        )
        self._conn.commit()

    def create_or_update_session(
        self,
        content_session_id: str,
        project: str,
        prompt: str = "",
        platform_source: str = "rpa-harness",
        custom_title: str | None = None,
    ) -> dict[str, Any]:
        safe_prompt = redact_text(prompt)
        now_text, now_epoch = _now()
        existing = self._conn.execute(
            "SELECT id, memory_session_id, prompt_counter FROM sdk_sessions WHERE content_session_id = ?",
            (content_session_id,),
        ).fetchone()
        if existing:
            prompt_number = int(existing["prompt_counter"] or 0) + 1
            memory_session_id = existing["memory_session_id"]
            self._conn.execute(
                """
                UPDATE sdk_sessions
                SET project = ?, platform_source = ?, user_prompt = ?,
                    prompt_counter = ?, custom_title = COALESCE(?, custom_title)
                WHERE content_session_id = ?
                """,
                (
                    project,
                    platform_source,
                    safe_prompt,
                    prompt_number,
                    custom_title,
                    content_session_id,
                ),
            )
            session_db_id = existing["id"]
        else:
            prompt_number = 1
            memory_session_id = str(uuid.uuid4())
            cursor = self._conn.execute(
                """
                INSERT INTO sdk_sessions (
                    content_session_id, memory_session_id, project, platform_source,
                    user_prompt, started_at, started_at_epoch, status,
                    prompt_counter, custom_title
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    content_session_id,
                    memory_session_id,
                    project,
                    platform_source,
                    safe_prompt,
                    now_text,
                    now_epoch,
                    prompt_number,
                    custom_title,
                ),
            )
            session_db_id = cursor.lastrowid

        if safe_prompt:
            self._conn.execute(
                """
                INSERT INTO user_prompts (
                    content_session_id, project, prompt_number, prompt_text,
                    created_at, created_at_epoch
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (content_session_id, project, prompt_number, safe_prompt, now_text, now_epoch),
            )
        self._conn.commit()
        return {
            "sessionDbId": session_db_id,
            "memorySessionId": memory_session_id,
            "promptNumber": prompt_number,
        }

    def add_observation(
        self,
        content_session_id: str,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        tool_response: Any = None,
        cwd: str = "",
        agent_id: str | None = None,
        agent_type: str | None = None,
    ) -> dict[str, Any]:
        session = self._session_by_content_id(content_session_id)
        if not session:
            self.create_or_update_session(content_session_id, "rpa-harness", "")
            session = self._session_by_content_id(content_session_id)
        assert session is not None

        project = session["project"]
        memory_session_id = session["memory_session_id"]
        safe_input = redact_mapping(tool_input or {})
        safe_response = redact_value(tool_response)
        searchable_text = redact_text(
            json.dumps(
                {"tool_input": safe_input, "tool_response": safe_response},
                default=str,
            )
        )
        title = self._title_for(tool_name, safe_input, safe_response)
        concepts = self._concepts_for(tool_name, safe_input, safe_response)
        now_text, now_epoch = _now()
        content_hash = self._content_hash(memory_session_id, tool_name, safe_input, safe_response)

        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO observations (
                memory_session_id, project, text, type, title, subtitle, facts,
                narrative, concepts, files_read, files_modified, prompt_number,
                content_hash, agent_type, agent_id, metadata, created_at, created_at_epoch
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_session_id,
                project,
                searchable_text,
                "change",
                title,
                tool_name,
                _json([]),
                searchable_text,
                _json(concepts),
                _json(self._files_from(safe_input, "read")),
                _json(self._files_from(safe_input, "modified")),
                session["prompt_counter"] or 0,
                content_hash,
                agent_type,
                agent_id,
                _json({"cwd": redact_text(cwd), "tool_input": safe_input}),
                now_text,
                now_epoch,
            ),
        )
        self._conn.commit()
        return {"id": cursor.lastrowid, "status": "stored" if cursor.lastrowid else "duplicate"}

    def add_summary(
        self,
        content_session_id: str,
        last_assistant_message: str,
    ) -> dict[str, Any]:
        session = self._session_by_content_id(content_session_id)
        if not session:
            self.create_or_update_session(content_session_id, "rpa-harness", "")
            session = self._session_by_content_id(content_session_id)
        assert session is not None

        safe_message = redact_text(last_assistant_message)
        now_text, now_epoch = _now()
        cursor = self._conn.execute(
            """
            INSERT INTO session_summaries (
                memory_session_id, project, request, investigated, learned,
                completed, next_steps, files_read, files_edited, notes,
                prompt_number, created_at, created_at_epoch
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["memory_session_id"],
                session["project"],
                session["user_prompt"],
                safe_message,
                "",
                safe_message,
                "",
                _json([]),
                _json([]),
                "",
                session["prompt_counter"] or 0,
                now_text,
                now_epoch,
            ),
        )
        self._conn.execute(
            """
            UPDATE sdk_sessions
            SET completed_at = ?, completed_at_epoch = ?, status = 'completed'
            WHERE content_session_id = ?
            """,
            (now_text, now_epoch, content_session_id),
        )
        self._conn.commit()
        return {"id": cursor.lastrowid, "status": "stored"}

    def save_manual_memory(
        self,
        text: str,
        title: str | None,
        project: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content_session_id = f"manual-{project}"
        session = self.create_or_update_session(content_session_id, project, "Manual memory")
        response = {
            "title": title,
            "text": redact_text(text),
            "metadata": redact_mapping(metadata or {}),
        }
        return self.add_observation(
            content_session_id=content_session_id,
            tool_name="manual_memory",
            tool_input={"project": project, "title": title},
            tool_response=response,
        ) | {"title": title or redact_text(text, max_chars=60), "project": project}

    def search(
        self,
        query: str | None = None,
        project: str | None = None,
        result_type: str | None = None,
        obs_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "date_desc",
    ) -> dict[str, Any]:
        observations = []
        sessions = []
        prompts = []
        search_type = result_type or "all"

        if search_type in {"all", "observations"}:
            observations = self._search_observations(query, project, obs_type, limit, offset, order_by)
        if search_type in {"all", "sessions"}:
            sessions = self._search_summaries(query, project, limit, offset, order_by)
        if search_type in {"all", "prompts"}:
            prompts = self._search_prompts(query, project, limit, offset, order_by)

        return {
            "results": {
                "observations": observations,
                "sessions": sessions,
                "prompts": prompts,
            },
            "usedChroma": False,
            "strategy": "sqlite",
        }

    def timeline(
        self,
        anchor: int | None = None,
        query: str | None = None,
        project: str | None = None,
        depth_before: int = 3,
        depth_after: int = 3,
    ) -> dict[str, Any]:
        if anchor is None and query:
            found = self._search_observations(query, project, None, 1, 0, "date_desc")
            if found:
                anchor = found[0]["id"]
        if anchor is None:
            return {"anchor": None, "items": []}

        row = self._conn.execute(
            "SELECT created_at_epoch FROM observations WHERE id = ?",
            (anchor,),
        ).fetchone()
        if not row:
            return {"anchor": anchor, "items": []}

        before = self._timeline_rows(project, row["created_at_epoch"], "<", depth_before, "DESC")
        after = self._timeline_rows(project, row["created_at_epoch"], ">", depth_after, "ASC")
        center = self.get_observations([anchor]).get("observations", [])
        items = list(reversed(before)) + center + after
        return {"anchor": anchor, "items": items, "observations": items}

    def get_observations(
        self,
        ids: list[int],
        project: str | None = None,
        limit: int | None = None,
        order_by: str = "date_desc",
    ) -> dict[str, Any]:
        if not ids:
            return {"observations": []}
        placeholders = ",".join("?" for _ in ids)
        params: list[Any] = list(ids)
        where = f"id IN ({placeholders})"
        if project:
            where += " AND project = ?"
            params.append(project)
        order = "ASC" if order_by == "date_asc" else "DESC"
        sql = f"SELECT * FROM observations WHERE {where} ORDER BY created_at_epoch {order}"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return {"observations": [self._observation_dict(row) for row in rows]}

    def context_for_project(self, project: str, limit: int = 10) -> str:
        rows = self._conn.execute(
            """
            SELECT title, narrative, created_at
            FROM observations
            WHERE project = ?
            ORDER BY created_at_epoch DESC
            LIMIT ?
            """,
            (project, limit),
        ).fetchall()
        if not rows:
            return ""
        lines = ["## Relevant past RPA Memory"]
        for row in rows:
            lines.append(f"- {row['title']}: {row['narrative'][:240]}")
        return "\n".join(lines)

    def close(self) -> None:
        self._conn.close()

    def _session_by_content_id(self, content_session_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM sdk_sessions WHERE content_session_id = ?",
            (content_session_id,),
        ).fetchone()

    @staticmethod
    def _content_hash(memory_session_id: str, tool_name: str, tool_input: Any, tool_response: Any) -> str:
        raw = json.dumps([memory_session_id, tool_name, tool_input, tool_response], default=str, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _title_for(tool_name: str, tool_input: dict[str, Any], tool_response: Any) -> str:
        if isinstance(tool_response, dict) and tool_response.get("title"):
            return str(tool_response["title"])[:160]
        if isinstance(tool_response, dict) and tool_response.get("status"):
            return f"{tool_name}: {tool_response['status']}"[:160]
        return tool_name[:160]

    @staticmethod
    def _concepts_for(tool_name: str, tool_input: dict[str, Any], tool_response: Any) -> list[str]:
        concepts = {"rpa", tool_name.split(".", 1)[0]}
        if "selector" in tool_input:
            concepts.add("selector")
        if isinstance(tool_response, dict):
            if tool_response.get("status") == "failed":
                concepts.add("failure")
            if tool_response.get("healed_selector"):
                concepts.add("healing")
        return sorted(concept for concept in concepts if concept)

    @staticmethod
    def _files_from(data: dict[str, Any], mode: str) -> list[str]:
        keys = ("path", "file", "file_path")
        files = []
        for key in keys:
            value = data.get(key)
            if isinstance(value, str):
                files.append(redact_text(value))
        return files

    def _search_observations(
        self,
        query: str | None,
        project: str | None,
        obs_type: str | None,
        limit: int,
        offset: int,
        order_by: str,
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if query:
            where.append("(title LIKE ? OR narrative LIKE ? OR text LIKE ? OR concepts LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like, like])
        if project:
            where.append("project = ?")
            params.append(project)
        if obs_type:
            values = [item.strip() for item in obs_type.split(",") if item.strip()]
            if values:
                where.append(f"type IN ({','.join('?' for _ in values)})")
                params.extend(values)
        sql = "SELECT * FROM observations"
        if where:
            sql += " WHERE " + " AND ".join(where)
        order_params: list[Any] = []
        if query and order_by != "date_asc":
            sql += """
            ORDER BY
                CASE
                    WHEN title LIKE ? THEN 0
                    WHEN concepts LIKE ? THEN 1
                    WHEN narrative LIKE ? THEN 2
                    WHEN text LIKE ? THEN 3
                    ELSE 4
                END,
                created_at_epoch DESC
            """
            like = f"%{query}%"
            order_params.extend([like, like, like, like])
        else:
            sql += " ORDER BY created_at_epoch " + ("ASC" if order_by == "date_asc" else "DESC")
        sql += " LIMIT ? OFFSET ?"
        params.extend(order_params)
        params.extend([limit, offset])
        return [self._observation_index_dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def _search_summaries(
        self,
        query: str | None,
        project: str | None,
        limit: int,
        offset: int,
        order_by: str,
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if query:
            where.append("(request LIKE ? OR investigated LIKE ? OR completed LIKE ? OR learned LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like, like])
        if project:
            where.append("project = ?")
            params.append(project)
        sql = "SELECT * FROM session_summaries"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at_epoch " + ("ASC" if order_by == "date_asc" else "DESC")
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def _search_prompts(
        self,
        query: str | None,
        project: str | None,
        limit: int,
        offset: int,
        order_by: str,
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if query:
            where.append("prompt_text LIKE ?")
            params.append(f"%{query}%")
        if project:
            where.append("project = ?")
            params.append(project)
        sql = "SELECT * FROM user_prompts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at_epoch " + ("ASC" if order_by == "date_asc" else "DESC")
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def _timeline_rows(
        self,
        project: str | None,
        anchor_epoch: int,
        op: str,
        limit: int,
        order: str,
    ) -> list[dict[str, Any]]:
        where = [f"created_at_epoch {op} ?"]
        params: list[Any] = [anchor_epoch]
        if project:
            where.append("project = ?")
            params.append(project)
        params.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT * FROM observations
            WHERE {' AND '.join(where)}
            ORDER BY created_at_epoch {order}
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._observation_dict(row) for row in rows]

    @staticmethod
    def _observation_index_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project": row["project"],
            "type": row["type"],
            "title": row["title"],
            "subtitle": row["subtitle"],
            "created_at": row["created_at"],
            "created_at_epoch": row["created_at_epoch"],
        }

    @staticmethod
    def _observation_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("facts", "concepts", "files_read", "files_modified"):
            try:
                data[key] = json.loads(data[key] or "[]")
            except json.JSONDecodeError:
                data[key] = []
        try:
            data["metadata"] = json.loads(data.get("metadata") or "{}")
        except json.JSONDecodeError:
            data["metadata"] = {}
        return data
