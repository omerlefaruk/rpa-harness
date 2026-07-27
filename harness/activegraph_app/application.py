"""Shared automation-application interface over ActiveGraph EventStore authority."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from activegraph import Event, Graph, InMemoryEventStore, Runtime
from activegraph.tools.context import ToolContext

from harness.activegraph_app.models import (
    ActionAttemptSummary,
    DefinitionVersionSummary,
    EvidenceReferenceSummary,
    RunSummary,
    VerificationSummary,
    WorkspaceInfo,
)
from harness.activegraph_app.pack import build_pack
from harness.activegraph_app.pack.tools import ReadProbeAdapter, make_read_probe_tool
from harness.activegraph_app.workspace import (
    ACTIVEGRAPH_VERSION,
    APPLICATION_INTERFACE_VERSION,
    EVENT_SCHEMA_VERSION,
    PACK_NAME,
    PACK_VERSION,
    PRODUCT_VERSION,
    WorkspaceError,
    WorkspaceWriteLock,
    initialize_workspace,
    read_manifest,
    workspace_paths,
)

StoreKind = Literal["sqlite", "memory"]


class ApplicationError(RuntimeError):
    """Domain failure visible at the application boundary."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _emit(runtime: Runtime, event_type: str, payload: dict[str, Any]) -> None:
    """Append a custom application lifecycle event to the authoritative log."""
    event = Event(
        id=runtime.graph.ids.event(),
        type=event_type,
        payload=payload,
        actor="automation-application",
    )
    runtime.graph.emit(event)


def _default_read_probe(target: str) -> dict[str, Any]:
    return {
        "value": f"value-for:{target}",
        "observed_at": _utc_now(),
        "redacted_snippet": f"target={target}",
    }


class AutomationApplication:
    """Deep module owning lifecycle transitions behind one stable interface."""

    def __init__(
        self,
        workspace: Path | str,
        *,
        store_kind: StoreKind = "sqlite",
        read_probe: ReadProbeAdapter | None = None,
        owner: str = "automation-application",
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.store_kind = store_kind
        self.read_probe = read_probe or _default_read_probe
        self.owner = owner
        self.paths = workspace_paths(self.workspace)
        self._memory_store: InMemoryEventStore | None = (
            InMemoryEventStore() if store_kind == "memory" else None
        )
        self._memory_runtime: Runtime | None = None

    def init_workspace(self) -> WorkspaceInfo:
        initialize_workspace(self.workspace)
        manifest = read_manifest(self.workspace)
        return WorkspaceInfo(
            path=str(self.paths.root),
            product_version=str(manifest.get("product_version", PRODUCT_VERSION)),
            activegraph_version=str(manifest.get("activegraph_version", ACTIVEGRAPH_VERSION)),
            pack_name=str(manifest.get("pack_name", PACK_NAME)),
            pack_version=str(manifest.get("pack_version", PACK_VERSION)),
            event_schema_version=str(manifest.get("event_schema_version", EVENT_SCHEMA_VERSION)),
            application_interface_version=str(
                manifest.get("application_interface_version", APPLICATION_INTERFACE_VERSION)
            ),
            event_store_path=str(self.paths.event_store),
        )

    def register_readonly_definition(
        self,
        *,
        name: str,
        target: str,
        success_check: str,
        expected_value: str | None = None,
        capability: str = "read_probe",
        action_class: str = "R0",
        definition_id: str | None = None,
        version: str = "1",
    ) -> DefinitionVersionSummary:
        if not success_check.strip():
            raise ApplicationError("success_check is required")
        if action_class not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ApplicationError(f"invalid action_class: {action_class}")
        if capability != "read_probe":
            raise ApplicationError(f"unknown capability for this slice: {capability}")

        def_id = definition_id or _new_id("def")
        body = {
            "definition_id": def_id,
            "version": version,
            "name": name,
            "capability": capability,
            "action_class": action_class,
            "target": target,
            "success_check": success_check,
            "expected_value": expected_value,
        }
        content_hash = _content_hash(body)
        record = {**body, "content_hash": content_hash}

        self._require_workspace()
        with self._writer():
            runtime, close = self._open_runtime(write=True)
            try:
                existing = [
                    obj
                    for obj in runtime.graph.all_objects()
                    if obj.type == "automation_definition"
                    and obj.data.get("definition_id") == def_id
                    and obj.data.get("version") == version
                ]
                if existing:
                    data = existing[0].data
                    return DefinitionVersionSummary(
                        definition_id=str(data["definition_id"]),
                        version=str(data["version"]),
                        content_hash=str(data["content_hash"]),
                        name=str(data["name"]),
                        action_class=str(data["action_class"]),
                        capability=str(data["capability"]),
                    )
                runtime.graph.add_object("automation_definition", record)
                _emit(
                    runtime,
                    "automation.definition_registered",
                    {
                        "definition_id": def_id,
                        "version": version,
                        "content_hash": content_hash,
                    },
                )
                runtime.run_until_idle()
            finally:
                close()

        # Durable export for operators; lifecycle authority remains EventStore.
        export_path = self.paths.definitions / f"{def_id}_v{version}.json"
        export_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return DefinitionVersionSummary(
            definition_id=def_id,
            version=version,
            content_hash=content_hash,
            name=name,
            action_class=action_class,
            capability=capability,
        )

    def execute_readonly_run(
        self,
        *,
        definition_id: str,
        version: str = "1",
        run_id: str | None = None,
    ) -> RunSummary:
        self._require_workspace()
        with self._writer():
            runtime, close = self._open_runtime(write=True)
            try:
                definition = self._find_definition(runtime, definition_id, version)
                rid = run_id or _new_id("run")
                runtime.graph.add_object(
                    "automation_run",
                    {
                        "run_id": rid,
                        "definition_id": definition_id,
                        "definition_version": version,
                        "status": "running",
                        "failure_kind": None,
                    },
                )
                _emit(
                    runtime,
                    "automation.run_started",
                    {"run_id": rid, "definition_id": definition_id, "version": version},
                )

                attempt_id = _new_id("attempt")
                runtime.graph.add_object(
                    "action_attempt",
                    {
                        "attempt_id": attempt_id,
                        "run_id": rid,
                        "capability": definition["capability"],
                        "action_class": definition["action_class"],
                        "status": "started",
                        "tool_output": {},
                    },
                )

                tool_output = self._invoke_read_probe(runtime, target=str(definition["target"]))
                runtime.graph.patch_object(
                    self._object_id(runtime, "action_attempt", "attempt_id", attempt_id),
                    {"status": "succeeded", "tool_output": tool_output},
                )
                _emit(
                    runtime,
                    "automation.action_attempted",
                    {
                        "run_id": rid,
                        "attempt_id": attempt_id,
                        "capability": definition["capability"],
                        "action_class": definition["action_class"],
                    },
                )

                evidence = self._write_evidence(
                    run_id=rid,
                    attempt_id=attempt_id,
                    tool_output=tool_output,
                )
                runtime.graph.add_object(
                    "evidence_reference",
                    {
                        "evidence_id": evidence["evidence_id"],
                        "run_id": rid,
                        "attempt_id": attempt_id,
                        "kind": evidence["kind"],
                        "path": evidence["path"],
                        "redacted": True,
                    },
                )
                _emit(
                    runtime,
                    "automation.evidence_recorded",
                    {
                        "run_id": rid,
                        "attempt_id": attempt_id,
                        "evidence_id": evidence["evidence_id"],
                        "path": evidence["path"],
                    },
                )

                verification = self._verify(definition, tool_output)
                runtime.graph.add_object(
                    "verification_result",
                    {
                        "verification_id": verification["verification_id"],
                        "attempt_id": attempt_id,
                        "run_id": rid,
                        "passed": verification["passed"],
                        "failure_kind": verification["failure_kind"],
                        "message": verification["message"],
                        "observed_value": verification["observed_value"],
                    },
                )
                _emit(
                    runtime,
                    "automation.verification_completed",
                    {
                        "run_id": rid,
                        "attempt_id": attempt_id,
                        "passed": verification["passed"],
                        "failure_kind": verification["failure_kind"],
                    },
                )

                run_obj_id = self._object_id(runtime, "automation_run", "run_id", rid)
                if verification["passed"]:
                    runtime.graph.patch_object(
                        run_obj_id,
                        {"status": "completed", "failure_kind": None},
                    )
                    _emit(
                        runtime,
                        "automation.run_completed",
                        {"run_id": rid, "status": "completed"},
                    )
                else:
                    runtime.graph.patch_object(
                        run_obj_id,
                        {
                            "status": "failed",
                            "failure_kind": verification["failure_kind"],
                        },
                    )
                    runtime.graph.patch_object(
                        self._object_id(runtime, "action_attempt", "attempt_id", attempt_id),
                        {"status": "failed"},
                    )
                    _emit(
                        runtime,
                        "automation.run_failed",
                        {
                            "run_id": rid,
                            "status": "failed",
                            "failure_kind": verification["failure_kind"],
                        },
                    )

                runtime.run_until_idle()
                return self._project_run(runtime, rid)
            finally:
                close()

    def inspect_run(self, run_id: str) -> RunSummary:
        """Read-only inspection. Does not take the write lock."""
        self._require_workspace()
        runtime, close = self._open_runtime(write=False)
        try:
            return self._project_run(runtime, run_id)
        finally:
            close()

    def _require_workspace(self) -> None:
        if not self.paths.manifest.exists():
            raise WorkspaceError(f"workspace is not initialized: {self.paths.root}")

    def _writer(self) -> WorkspaceWriteLock:
        return WorkspaceWriteLock(self.workspace, owner=self.owner)

    def _open_runtime(self, *, write: bool) -> tuple[Runtime, Callable[[], None]]:
        tools = (make_read_probe_tool(self.read_probe),)
        pack = build_pack(tools=tools)
        _ = write  # reserved: readers already skip the write lock

        if self.store_kind == "memory":
            assert self._memory_store is not None
            if self._memory_runtime is None:
                self._memory_runtime = Runtime(
                    Graph(),
                    store=self._memory_store,
                    tools=tools,
                    seed=0,
                )
                self._memory_runtime.load_pack(pack)
            return self._memory_runtime, lambda: None

        self.paths.event_store.parent.mkdir(parents=True, exist_ok=True)
        store_path = str(self.paths.event_store)
        if self.paths.event_store.exists() and self.paths.event_store.stat().st_size > 0:
            # Resume from the durable log without re-emitting pack.loaded.
            runtime = Runtime.load(store_path, tools=tools, seed=0)
            self._attach_host_tools(runtime, tools)
        else:
            runtime = Runtime(Graph(), persist_to=store_path, tools=tools, seed=0)
            runtime.load_pack(pack)

        def _close() -> None:
            store = getattr(runtime, "store", None)
            if store is not None and hasattr(store, "close"):
                try:
                    store.close()
                except Exception:
                    pass

        return runtime, _close

    def _attach_host_tools(self, runtime: Runtime, tools: tuple) -> None:
        """Register host-injected tools after resume without mutating the event log."""
        from dataclasses import replace

        pack_tools = list(getattr(runtime, "_pack_tools", []) or [])
        existing = {getattr(t, "name", "") for t in pack_tools}
        for tool in tools:
            short = tool.name.removeprefix(f"{PACK_NAME}.")
            canonical = f"{PACK_NAME}.{short}"
            if canonical in existing or short in existing:
                continue
            pack_tools.append(replace(tool, name=canonical))
            existing.add(canonical)
        runtime._pack_tools = pack_tools  # type: ignore[attr-defined]
        ensure = getattr(runtime, "_ensure_registry", None)
        if callable(ensure):
            ensure()

    def _find_definition(self, runtime: Runtime, definition_id: str, version: str) -> dict[str, Any]:
        for obj in runtime.graph.all_objects():
            if (
                obj.type == "automation_definition"
                and obj.data.get("definition_id") == definition_id
                and obj.data.get("version") == version
            ):
                return dict(obj.data)
        raise ApplicationError(f"definition not found: {definition_id}@v{version}")

    def _object_id(self, runtime: Runtime, obj_type: str, key: str, value: str) -> str:
        for obj in runtime.graph.all_objects():
            if obj.type == obj_type and obj.data.get(key) == value:
                return obj.id
        raise ApplicationError(f"{obj_type} not found for {key}={value}")

    def _invoke_read_probe(self, runtime: Runtime, *, target: str) -> dict[str, Any]:
        ensure = getattr(runtime, "_ensure_registry", None)
        if callable(ensure):
            ensure()
        tool = None
        for name in ("rpa_automation.read_probe", "read_probe"):
            try:
                tool = runtime.get_tool(name)
                break
            except Exception:
                tool = None
        if tool is None:
            # Fall back to the host-injected adapter tool when registry is cold.
            tool = make_read_probe_tool(self.read_probe)
        args = tool.input_schema(target=target)
        ctx = ToolContext(
            behavior_name="automation-application",
            event_id="application",
            frame=None,
            idempotency_key="",
            timeout_seconds=float(getattr(tool, "timeout_seconds", 30.0)),
            external_io_mode="runtime_recorded",
        )
        # Record tool lifecycle events for auditability.
        _emit(
            runtime,
            "tool.requested",
            {
                "tool": getattr(tool, "name", "read_probe"),
                "args": args.model_dump(),
                "source": "automation-application",
            },
        )
        try:
            result = tool.fn(args, ctx)
        except Exception as exc:
            _emit(
                runtime,
                "tool.responded",
                {
                    "tool": getattr(tool, "name", "read_probe"),
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise ApplicationError(f"read_probe failed: {exc}") from exc

        payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        _emit(
            runtime,
            "tool.responded",
            {
                "tool": getattr(tool, "name", "read_probe"),
                "output": payload,
            },
        )
        return payload

    def _write_evidence(
        self,
        *,
        run_id: str,
        attempt_id: str,
        tool_output: dict[str, Any],
    ) -> dict[str, str]:
        self.paths.evidence.mkdir(parents=True, exist_ok=True)
        evidence_id = _new_id("ev")
        path = self.paths.evidence / f"{run_id}_{attempt_id}.json"
        redacted = {
            "evidence_id": evidence_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "value": tool_output.get("value"),
            "observed_at": tool_output.get("observed_at"),
            "redacted_snippet": tool_output.get("redacted_snippet", ""),
            "redacted": True,
        }
        path.write_text(json.dumps(redacted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "evidence_id": evidence_id,
            "kind": "read_probe_json",
            "path": str(path.relative_to(self.paths.root)).replace("\\", "/"),
        }

    def _verify(self, definition: dict[str, Any], tool_output: dict[str, Any]) -> dict[str, Any]:
        check = str(definition.get("success_check") or "")
        expected = definition.get("expected_value")
        observed = tool_output.get("value")
        verification_id = _new_id("ver")

        if check == "equals":
            passed = observed == expected
            failure_kind = None if passed else "verification_mismatch"
            message = "observed value equals expected" if passed else "observed value does not equal expected"
        elif check == "exists":
            passed = observed is not None and str(observed) != ""
            failure_kind = None if passed else "verification_missing"
            message = "value present" if passed else "value missing"
        else:
            passed = False
            failure_kind = "unknown_success_check"
            message = f"unsupported success_check: {check}"

        return {
            "verification_id": verification_id,
            "passed": passed,
            "failure_kind": failure_kind,
            "message": message,
            "observed_value": None if observed is None else str(observed),
        }

    def _project_run(self, runtime: Runtime, run_id: str) -> RunSummary:
        run_obj = None
        for obj in runtime.graph.all_objects():
            if obj.type == "automation_run" and obj.data.get("run_id") == run_id:
                run_obj = obj
                break
        if run_obj is None:
            raise ApplicationError(f"run not found: {run_id}")

        attempts: list[ActionAttemptSummary] = []
        verifications = {
            obj.data.get("attempt_id"): obj.data
            for obj in runtime.graph.all_objects()
            if obj.type == "verification_result" and obj.data.get("run_id") == run_id
        }
        evidence_by_attempt: dict[str, list[EvidenceReferenceSummary]] = {}
        for obj in runtime.graph.all_objects():
            if obj.type == "evidence_reference" and obj.data.get("run_id") == run_id:
                attempt_id = str(obj.data.get("attempt_id"))
                evidence_by_attempt.setdefault(attempt_id, []).append(
                    EvidenceReferenceSummary(
                        evidence_id=str(obj.data.get("evidence_id")),
                        kind=str(obj.data.get("kind")),
                        path=str(obj.data.get("path")),
                        redacted=bool(obj.data.get("redacted", True)),
                    )
                )

        for obj in runtime.graph.all_objects():
            if obj.type != "action_attempt" or obj.data.get("run_id") != run_id:
                continue
            attempt_id = str(obj.data.get("attempt_id"))
            ver = verifications.get(attempt_id)
            verification = None
            if ver is not None:
                verification = VerificationSummary(
                    verification_id=str(ver.get("verification_id")),
                    passed=bool(ver.get("passed")),
                    failure_kind=ver.get("failure_kind"),
                    message=str(ver.get("message") or ""),
                )
            attempts.append(
                ActionAttemptSummary(
                    attempt_id=attempt_id,
                    capability=str(obj.data.get("capability")),
                    status=str(obj.data.get("status")),
                    action_class=str(obj.data.get("action_class")),
                    verification=verification,
                    evidence=tuple(evidence_by_attempt.get(attempt_id, ())),
                )
            )

        try:
            event_count = len(list(runtime.graph.events)) if hasattr(runtime.graph, "events") else 0
        except Exception:
            event_count = 0
        store = getattr(runtime, "store", None)
        if store is not None and hasattr(store, "count"):
            try:
                event_count = int(store.count())
            except Exception:
                pass

        return RunSummary(
            run_id=run_id,
            definition_id=str(run_obj.data.get("definition_id")),
            definition_version=str(run_obj.data.get("definition_version")),
            status=str(run_obj.data.get("status")),
            failure_kind=run_obj.data.get("failure_kind"),
            attempts=tuple(attempts),
            event_count=event_count,
        )
