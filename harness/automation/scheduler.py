"""Windows Task Scheduler registrations pinned to workspace runtime + definition version."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness.security import redact_value


class SchedulerCapabilityError(RuntimeError):
    code = "scheduler_capability_unavailable"


@dataclass(frozen=True)
class ScheduledTaskSpec:
    task_name: str
    workspace: str
    runtime_version: str
    definition_id: str
    definition_version: int
    target_scope: str
    trigger: str
    enabled: bool = True
    actor: str = "scheduler"
    credential_handles: tuple[str, ...] = ()
    revision_content_hash: str = ""

    def cli_args(self) -> list[str]:
        # No secret values in scheduler arguments.
        return [
            "--automation-workspace",
            self.workspace,
            "--automation-execute-version",
            f"{self.definition_id}@{self.definition_version}",
            "--automation-target-scope",
            self.target_scope,
            "--automation-trigger",
            self.trigger,
            "--automation-runtime-version",
            self.runtime_version,
        ]


class WindowsTaskSchedulerAdapter:
    """Boundary for the real Windows Task Scheduler integration."""

    @staticmethod
    def require_interactive_windows() -> None:
        if not sys.platform.startswith("win"):
            raise SchedulerCapabilityError(
                "Windows Task Scheduler requires an interactive Windows host"
            )

    def register(self, spec: ScheduledTaskSpec) -> None:
        self.require_interactive_windows()
        raise NotImplementedError("Task Scheduler COM adapter is platform-owned")

    def remove(self, task_name: str) -> None:
        self.require_interactive_windows()
        raise NotImplementedError("Task Scheduler COM adapter is platform-owned")


@dataclass
class ScheduledTaskRecord:
    spec: ScheduledTaskSpec
    registration_id: str
    updated_at: str
    last_run_id: str | None = None
    last_status: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return redact_value(
            {
                "registration_id": self.registration_id,
                "spec": asdict(self.spec),
                "cli_args": self.spec.cli_args(),
                "updated_at": self.updated_at,
                "last_run_id": self.last_run_id,
                "last_status": self.last_status,
                "last_error": self.last_error,
            }
        )


class TaskSchedulerService:
    """Idempotent scheduler registration projection for a workspace."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.path = self.workspace / "data" / "scheduled-tasks.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, ScheduledTaskRecord] = {}
        self._load()

    def register(self, spec: ScheduledTaskSpec) -> ScheduledTaskRecord:
        existing = self._tasks.get(spec.task_name)
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            record = ScheduledTaskRecord(
                spec=spec,
                registration_id=existing.registration_id,
                updated_at=now,
                last_run_id=existing.last_run_id,
                last_status=existing.last_status,
                last_error=existing.last_error,
            )
        else:
            record = ScheduledTaskRecord(
                spec=spec,
                registration_id=f"sched_{uuid4().hex}",
                updated_at=now,
            )
        self._tasks[spec.task_name] = record
        self._save()
        return record

    def get(self, task_name: str) -> ScheduledTaskRecord | None:
        return self._tasks.get(task_name)

    def list_tasks(self) -> tuple[ScheduledTaskRecord, ...]:
        return tuple(self._tasks.values())

    def disable(self, task_name: str) -> ScheduledTaskRecord:
        record = self._require(task_name)
        disabled = ScheduledTaskSpec(**{**asdict(record.spec), "enabled": False})
        return self.register(disabled)

    def mark_launch(
        self,
        task_name: str,
        *,
        run_id: str | None,
        status: str,
        error: str | None = None,
    ) -> ScheduledTaskRecord:
        record = self._require(task_name)
        updated = ScheduledTaskRecord(
            spec=record.spec,
            registration_id=record.registration_id,
            updated_at=datetime.now(UTC).isoformat(),
            last_run_id=run_id,
            last_status=status,
            last_error=error,
        )
        self._tasks[task_name] = updated
        self._save()
        return updated

    def validate_launch(
        self,
        task_name: str,
        *,
        runtime_version: str,
        credentials_present: bool,
        workspace_locked: bool,
        approval_expired: bool = False,
    ) -> dict[str, Any]:
        record = self._require(task_name)
        if not record.spec.enabled:
            return {"ok": False, "error": "disabled"}
        if workspace_locked:
            return {"ok": False, "error": "locked-workspace"}
        if not credentials_present:
            return {"ok": False, "error": "missing-credential"}
        if approval_expired:
            return {"ok": False, "error": "expired"}
        if record.spec.runtime_version != runtime_version:
            return {"ok": False, "error": "runtime-mismatch-rollback-required"}
        return {
            "ok": True,
            "cli_args": record.spec.cli_args(),
            "definition_id": record.spec.definition_id,
            "definition_version": record.spec.definition_version,
        }

    def _require(self, task_name: str) -> ScheduledTaskRecord:
        record = self._tasks.get(task_name)
        if record is None:
            raise KeyError(task_name)
        return record

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for item in raw.get("tasks", ()):
            spec = ScheduledTaskSpec(**item["spec"])
            self._tasks[spec.task_name] = ScheduledTaskRecord(
                spec=spec,
                registration_id=item["registration_id"],
                updated_at=item["updated_at"],
                last_run_id=item.get("last_run_id"),
                last_status=item.get("last_status"),
                last_error=item.get("last_error"),
            )

    def _save(self) -> None:
        payload = {"tasks": [record.to_dict() for record in self._tasks.values()]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
