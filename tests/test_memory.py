"""Tests for memory database."""
import os
import tempfile
from harness.memory.database import MemoryDatabase


def test_memory_db_create():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = MemoryDatabase(path)
        assert db.db_path.exists()
        db.close()
    finally:
        os.unlink(path)


def test_memory_session_lifecycle():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = MemoryDatabase(path)
        session_id = db.create_session("s1", "test_workflow", "test task", "{}")
        assert session_id == "s1"

        db.end_session("s1", "passed", 5, 5, 0, 0, "all good")
        sessions = db.get_recent_sessions(limit=5)
        assert len(sessions) >= 1
        assert sessions[0]["status"] == "passed"
        db.close()
    finally:
        os.unlink(path)


def test_memory_add_observation():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = MemoryDatabase(path)
        db.insert_triggers()
        db.create_session("s2", "test", "task", "{}")
        obs_id = db.add_observation(
            session_id="s2", step_id=1, step_name="click_login",
            action="click", tool_used="browser_click",
            success=True, selector_used="#login-btn",
        )
        assert obs_id > 0
        db.close()
    finally:
        os.unlink(path)


def test_memory_selector_cache():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = MemoryDatabase(path)
        sid = db.upsert_selector(
            url_pattern="example.com/login",
            selector="#login-btn",
            selector_type="css",
            element_description="Login button",
            success=True,
        )
        assert sid > 0

        selectors = db.get_selectors("example.com/login", limit=5)
        assert len(selectors) >= 1
        assert selectors[0]["selector"] == "#login-btn"

        # Second insert should update
        sid2 = db.upsert_selector(
            url_pattern="example.com/login",
            selector="#login-btn",
            success=True,
        )
        assert sid2 == sid

        db.close()
    finally:
        os.unlink(path)


def test_memory_search():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = MemoryDatabase(path)
        db.insert_triggers()
        db.create_session("s3", "test", "login task", "{}")
        db.add_observation(
            session_id="s3", step_id=1, step_name="click submit",
            action="click", tool_used="browser_click",
            selector_used="button[type='submit']",
            success=True,
        )

        results = db.search("submit", search_type="all", limit=5)
        assert len(results) > 0
        db.close()
    finally:
        os.unlink(path)


def test_memory_error_patterns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = MemoryDatabase(path)
        db.update_error_pattern(
            error_signature="selector_not_found",
            error_message="Element #old-btn not found",
            error_category="TRANSIENT",
            recovery_strategy="use alternative selector",
            success=True,
        )
        db.update_error_pattern(
            error_signature="selector_not_found",
            error_message="Element #old-btn not found again",
            error_category="TRANSIENT",
            recovery_strategy="use alternative selector",
            success=False,
        )

        results = db.search("selector_not_found", search_type="error", limit=5)
        assert len(results) >= 1
        db.close()
    finally:
        os.unlink(path)
