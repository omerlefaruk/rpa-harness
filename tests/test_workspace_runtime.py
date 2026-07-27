"""Windows-oriented integration tests for pinned workspace runtime lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.automation.workspace_runtime import (
    WorkspaceRuntimeError,
    WorkspaceRuntimeIncompatibleError,
    WorkspaceRuntimeManager,
    default_manifest,
)


def test_initialize_is_idempotent_and_preserves_operator_state(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    manager = WorkspaceRuntimeManager(workspace)
    first = manager.initialize()
    assert first.active is not None
    assert first.active.release_source.startswith("pypi:")
    assert not first.active.release_source.startswith("branch:")

    marker = workspace / "definitions" / "operator.json"
    marker.write_text('{"keep": true}\n', encoding="utf-8")
    (workspace / "evidence" / "note.txt").write_text("ev\n", encoding="utf-8")
    (workspace / "credentials" / "vault.txt").write_text("handle-only\n", encoding="utf-8")
    (workspace / "policy" / "policy.json").write_text("{}\n", encoding="utf-8")

    second = manager.initialize()
    assert second.active == first.active
    assert marker.read_text(encoding="utf-8") == '{"keep": true}\n'
    assert (workspace / "evidence" / "note.txt").exists()
    assert (workspace / "credentials" / "vault.txt").exists()
    assert (workspace / "policy" / "policy.json").exists()


def test_upgrade_switches_active_and_retains_previous(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    manager = WorkspaceRuntimeManager(workspace)
    manager.initialize(manifest=default_manifest(product_version="0.1.0"))

    upgraded = manager.upgrade(
        default_manifest(
            product_version="0.2.0",
            release_source="pypi:rpa-harness==0.2.0+activegraph==1.10.0",
        )
    )
    assert upgraded.active is not None
    assert upgraded.previous is not None
    assert upgraded.active.product_version == "0.2.0"
    assert upgraded.previous.product_version == "0.1.0"
    assert (workspace / "runtimes" / "0.2.0" / "runtime_manifest.json").exists()


def test_failed_upgrade_leaves_active_and_writes_diagnostic(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    manager = WorkspaceRuntimeManager(workspace)
    manager.initialize(manifest=default_manifest(product_version="0.1.0"))

    with pytest.raises(WorkspaceRuntimeError, match="validation failed"):
        manager.upgrade(
            default_manifest(product_version="0.9.0"),
            fail=True,
            diagnostic="validation failed",
        )

    status = manager.status()
    assert status.active is not None
    assert status.active.product_version == "0.1.0"
    diagnostic = workspace / "diagnostics" / "last_failed_upgrade.json"
    assert diagnostic.exists()
    payload = json.loads(diagnostic.read_text(encoding="utf-8"))
    assert payload["active_runtime"]["product_version"] == "0.1.0"
    assert "validation failed" in payload["error"]


def test_rollback_restores_previous_without_touching_event_history(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    manager = WorkspaceRuntimeManager(workspace)
    manager.initialize(manifest=default_manifest(product_version="0.1.0"))
    events = workspace / "data" / "automation-events.sqlite"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_bytes(b"event-log-bytes")

    manager.upgrade(default_manifest(product_version="0.2.0"))
    rolled = manager.rollback()
    assert rolled.active is not None
    assert rolled.active.product_version == "0.1.0"
    assert rolled.previous is not None
    assert rolled.previous.product_version == "0.2.0"
    assert events.read_bytes() == b"event-log-bytes"


def test_incompatible_event_schema_fails_before_activation(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    manager = WorkspaceRuntimeManager(workspace)
    manager.initialize(manifest=default_manifest(event_schema_version="1"))

    with pytest.raises(WorkspaceRuntimeIncompatibleError) as excinfo:
        manager.upgrade(default_manifest(product_version="0.3.0", event_schema_version="2"))
    assert "operator_action" in dir(excinfo.value)
    assert "event schema" in excinfo.value.operator_action.lower() or "export" in excinfo.value.operator_action.lower()
    assert manager.status().active is not None
    assert manager.status().active.product_version == "0.1.0"


def test_writer_lock_is_exclusive(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    manager = WorkspaceRuntimeManager(workspace)
    manager.initialize()
    fd = manager.acquire_writer_lock()
    try:
        with pytest.raises(WorkspaceRuntimeError, match="already active"):
            manager.acquire_writer_lock()
    finally:
        manager.release_writer_lock(fd)
