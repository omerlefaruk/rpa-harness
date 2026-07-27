"""Workspace layout, version manifest, and single-writer locking."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PRODUCT_VERSION = "0.2.0"
ACTIVEGRAPH_VERSION = "1.10.0"
PACK_NAME = "rpa_automation"
PACK_VERSION = "0.1.0"
EVENT_SCHEMA_VERSION = "1"
APPLICATION_INTERFACE_VERSION = "1.0.0"

MANIFEST_NAME = "workspace_manifest.json"
LOCK_NAME = "workspace.write.lock"
EVENT_STORE_REL = Path("state") / "events.sqlite"
EVIDENCE_REL = Path("evidence")
DEFINITIONS_REL = Path("definitions")


class WorkspaceError(RuntimeError):
    """Workspace lifecycle failure."""


class WorkspaceLockError(WorkspaceError):
    """Raised when a second write-capable runtime cannot be admitted."""


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    manifest: Path
    lock: Path
    event_store: Path
    evidence: Path
    definitions: Path


def workspace_paths(root: Path | str) -> WorkspacePaths:
    base = Path(root).resolve()
    return WorkspacePaths(
        root=base,
        manifest=base / MANIFEST_NAME,
        lock=base / LOCK_NAME,
        event_store=base / EVENT_STORE_REL,
        evidence=base / EVIDENCE_REL,
        definitions=base / DEFINITIONS_REL,
    )


def default_manifest() -> dict[str, Any]:
    return {
        "product_version": PRODUCT_VERSION,
        "activegraph_version": ACTIVEGRAPH_VERSION,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "pack_name": PACK_NAME,
        "pack_version": PACK_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "application_interface_version": APPLICATION_INTERFACE_VERSION,
    }


def initialize_workspace(root: Path | str) -> WorkspacePaths:
    """Create workspace directories and manifest. Idempotent for operator state."""
    paths = workspace_paths(root)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.evidence.mkdir(parents=True, exist_ok=True)
    paths.definitions.mkdir(parents=True, exist_ok=True)
    paths.event_store.parent.mkdir(parents=True, exist_ok=True)

    if paths.manifest.exists():
        # Preserve operator definitions/evidence/policy; only ensure layout.
        existing = json.loads(paths.manifest.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise WorkspaceError("workspace_manifest.json is not an object")
        return paths

    paths.manifest.write_text(
        json.dumps(default_manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def read_manifest(root: Path | str) -> dict[str, Any]:
    paths = workspace_paths(root)
    if not paths.manifest.exists():
        raise WorkspaceError(f"workspace is not initialized: {paths.root}")
    data = json.loads(paths.manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise WorkspaceError("workspace_manifest.json is not an object")
    return data


class WorkspaceWriteLock:
    """Exclusive write-capable runtime lock using an atomic create file."""

    def __init__(self, root: Path | str, *, owner: str) -> None:
        self.paths = workspace_paths(root)
        self.owner = owner
        self._held = False

    def acquire(self) -> None:
        if self._held:
            return
        self.paths.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "owner": self.owner,
            "pid": os.getpid(),
            "acquired_at": time.time(),
        }
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(str(self.paths.lock), flags)
        except FileExistsError as exc:
            detail = ""
            try:
                detail = self.paths.lock.read_text(encoding="utf-8").strip()
            except OSError:
                detail = "(unreadable)"
            raise WorkspaceLockError(
                f"workspace already has a write-capable runtime: {detail}"
            ) from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True))
        except Exception:
            try:
                self.paths.lock.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        try:
            self.paths.lock.unlink(missing_ok=True)
        finally:
            self._held = False

    def __enter__(self) -> WorkspaceWriteLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
