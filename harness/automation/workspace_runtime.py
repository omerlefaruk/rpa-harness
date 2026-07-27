"""Pinned workspace runtime install, upgrade, and rollback."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.security import redact_value

PRODUCT_VERSION = "0.1.0"
ACTIVEGRAPH_VERSION = "1.10.0"
PACK_NAME = "rpa_automation"
PACK_VERSION = "0.1.0"
EVENT_SCHEMA_VERSION = "1"
APPLICATION_INTERFACE_VERSION = "1.0.0"
DEFAULT_RELEASE_SOURCE = f"pypi:rpa-harness=={PRODUCT_VERSION}+activegraph=={ACTIVEGRAPH_VERSION}"

OPERATOR_DIRS = ("definitions", "evidence", "credentials", "policy")
ACTIVE_POINTER = "active_runtime.json"
PREVIOUS_POINTER = "previous_runtime.json"
RUNTIME_ROOT = Path("runtimes")
LOCK_NAME = ".automation-runtime.lock"


class WorkspaceRuntimeError(RuntimeError):
    """Workspace runtime lifecycle failure."""


class WorkspaceRuntimeIncompatibleError(WorkspaceRuntimeError):
    """Raised when an upgrade is incompatible with retained event/pack schema."""

    def __init__(self, message: str, *, operator_action: str) -> None:
        super().__init__(message)
        self.operator_action = operator_action


@dataclass(frozen=True)
class RuntimeManifest:
    product_version: str
    activegraph_version: str
    python_version: str
    pack_name: str
    pack_version: str
    event_schema_version: str
    application_interface_version: str
    release_source: str
    installed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceStatus:
    workspace: str
    active: RuntimeManifest | None
    previous: RuntimeManifest | None
    writer_lock_held: bool
    operator_dirs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "active": None if self.active is None else self.active.to_dict(),
            "previous": None if self.previous is None else self.previous.to_dict(),
            "writer_lock_held": self.writer_lock_held,
            "operator_dirs": list(self.operator_dirs),
        }


def current_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def default_manifest(
    *,
    product_version: str = PRODUCT_VERSION,
    activegraph_version: str = ACTIVEGRAPH_VERSION,
    pack_version: str = PACK_VERSION,
    event_schema_version: str = EVENT_SCHEMA_VERSION,
    application_interface_version: str = APPLICATION_INTERFACE_VERSION,
    release_source: str = DEFAULT_RELEASE_SOURCE,
    python_version: str | None = None,
) -> RuntimeManifest:
    return RuntimeManifest(
        product_version=product_version,
        activegraph_version=activegraph_version,
        python_version=python_version or current_python_version(),
        pack_name=PACK_NAME,
        pack_version=pack_version,
        event_schema_version=event_schema_version,
        application_interface_version=application_interface_version,
        release_source=release_source,
        installed_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )


class WorkspaceRuntimeManager:
    """Install and switch immutable, version-pinned workspace runtimes."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.runtime_root = self.workspace / RUNTIME_ROOT
        self.active_path = self.workspace / ACTIVE_POINTER
        self.previous_path = self.workspace / PREVIOUS_POINTER
        self.lock_path = self.workspace / LOCK_NAME

    def initialize(
        self,
        *,
        release_source: str = DEFAULT_RELEASE_SOURCE,
        manifest: RuntimeManifest | None = None,
    ) -> WorkspaceStatus:
        """Idempotent install. Never overwrites operator state."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        for name in OPERATOR_DIRS:
            (self.workspace / name).mkdir(exist_ok=True)
        (self.workspace / "data").mkdir(exist_ok=True)
        self.runtime_root.mkdir(exist_ok=True)

        if self.active_path.exists():
            return self.status()

        active = manifest or default_manifest(release_source=release_source)
        self._write_runtime(active)
        self._atomic_write_json(self.active_path, active.to_dict())
        return self.status()

    def status(self) -> WorkspaceStatus:
        return WorkspaceStatus(
            workspace=str(self.workspace),
            active=self._read_pointer(self.active_path),
            previous=self._read_pointer(self.previous_path),
            writer_lock_held=self.lock_path.exists(),
            operator_dirs=OPERATOR_DIRS,
        )

    def upgrade(
        self,
        target: RuntimeManifest,
        *,
        fail: bool = False,
        diagnostic: str | None = None,
    ) -> WorkspaceStatus:
        """Stage and validate a new runtime, then atomically switch active."""
        current = self._require_active()
        self._assert_compatible(current, target)

        stage_dir = self.runtime_root / f"stage_{target.product_version}_{os.getpid()}"
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
        stage_dir.mkdir(parents=True)

        try:
            if fail:
                raise WorkspaceRuntimeError(diagnostic or "staged runtime validation failed")
            self._materialize_runtime(stage_dir, target)
            # Promote stage to versioned runtime directory.
            final_dir = self._runtime_dir(target)
            if final_dir.exists():
                shutil.rmtree(final_dir)
            stage_dir.rename(final_dir)

            if self.active_path.exists():
                self._atomic_write_json(self.previous_path, current.to_dict())
            self._atomic_write_json(self.active_path, target.to_dict())
        except Exception as exc:
            self._record_failed_upgrade(current, target, exc)
            # Leave previous active untouched.
            if stage_dir.exists():
                shutil.rmtree(stage_dir, ignore_errors=True)
            raise
        return self.status()

    def rollback(self) -> WorkspaceStatus:
        """Restore previous compatible runtime without rewriting event history."""
        current = self._require_active()
        previous = self._read_pointer(self.previous_path)
        if previous is None:
            raise WorkspaceRuntimeError("no previous runtime is available to roll back to")
        self._assert_compatible(previous, current, for_rollback=True)

        # Swap pointers only; event store under data/ is retained.
        self._atomic_write_json(self.active_path, previous.to_dict())
        self._atomic_write_json(self.previous_path, current.to_dict())
        return self.status()

    def acquire_writer_lock(self) -> int:
        self.workspace.mkdir(parents=True, exist_ok=True)
        try:
            return os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise WorkspaceRuntimeError(
                f"A write-capable automation runtime is already active for {self.workspace}"
            ) from exc

    def release_writer_lock(self, fd: int | None) -> None:
        if fd is not None:
            os.close(fd)
        self.lock_path.unlink(missing_ok=True)

    def _require_active(self) -> RuntimeManifest:
        active = self._read_pointer(self.active_path)
        if active is None:
            raise WorkspaceRuntimeError("workspace has no active runtime; initialize first")
        return active

    def _read_pointer(self, path: Path) -> RuntimeManifest | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeManifest(**data)

    def _runtime_dir(self, manifest: RuntimeManifest) -> Path:
        stamp = manifest.product_version.replace("/", "_")
        return self.runtime_root / stamp

    def _write_runtime(self, manifest: RuntimeManifest) -> Path:
        path = self._runtime_dir(manifest)
        self._materialize_runtime(path, manifest)
        return path

    def _materialize_runtime(self, path: Path, manifest: RuntimeManifest) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "runtime_manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # Immutable release marker — never a floating branch name.
        (path / "RELEASE_SOURCE").write_text(manifest.release_source + "\n", encoding="utf-8")

    def _assert_compatible(
        self,
        baseline: RuntimeManifest,
        candidate: RuntimeManifest,
        *,
        for_rollback: bool = False,
    ) -> None:
        if candidate.event_schema_version != baseline.event_schema_version:
            action = (
                "export evidence, provision a new workspace for the new event schema, "
                "and re-register definitions"
                if not for_rollback
                else "restore from backup; event schema drift blocks rollback"
            )
            raise WorkspaceRuntimeIncompatibleError(
                "incompatible event schema version: "
                f"{baseline.event_schema_version} -> {candidate.event_schema_version}",
                operator_action=action,
            )
        if candidate.pack_name != baseline.pack_name:
            raise WorkspaceRuntimeIncompatibleError(
                f"incompatible pack: {baseline.pack_name} -> {candidate.pack_name}",
                operator_action="install a runtime that retains the same first-party pack name",
            )

    def _record_failed_upgrade(
        self,
        current: RuntimeManifest,
        target: RuntimeManifest,
        exc: BaseException,
    ) -> None:
        diagnostic_dir = self.workspace / "diagnostics"
        diagnostic_dir.mkdir(parents=True, exist_ok=True)
        path = diagnostic_dir / "last_failed_upgrade.json"
        payload = redact_value(
            {
                "failed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "active_runtime": current.to_dict(),
                "target_runtime": target.to_dict(),
                "error": str(exc),
                "error_type": type(exc).__name__,
                "operator_action": getattr(
                    exc,
                    "operator_action",
                    "retry upgrade after fixing validation errors; active runtime unchanged",
                ),
            }
        )
        self._atomic_write_json(path, payload)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
