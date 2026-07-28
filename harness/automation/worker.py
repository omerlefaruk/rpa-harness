"""Versioned, JSON-only worker boundary for immutable automation snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "rpa-worker-v2"


class WorkerProtocolError(RuntimeError):
    code = "automation_worker_protocol_error"


class WorkerTimeoutError(WorkerProtocolError):
    code = "automation_worker_timeout"


@dataclass(frozen=True)
class WorkerRequest:
    request_id: str
    snapshot_path: str
    expected_source_hash: str
    payload: dict[str, Any] = None  # type: ignore[assignment]
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.payload is None:
            object.__setattr__(self, "payload", {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "snapshot_path": self.snapshot_path,
            "expected_source_hash": self.expected_source_hash,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class WorkerResponse:
    request_id: str
    ok: bool
    value: Any = None
    error_code: str | None = None
    error: str | None = None
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "ok": self.ok,
            "value": self.value,
            "error_code": self.error_code,
            "error": self.error,
        }


def encode_request(request: WorkerRequest) -> str:
    return json.dumps(request.to_dict(), sort_keys=True, separators=(",", ":"))


def decode_response(raw: str, *, expected_request_id: str) -> WorkerResponse:
    try:
        value = json.loads(raw)
        if value.get("protocol_version") != PROTOCOL_VERSION:
            raise WorkerProtocolError("worker protocol version mismatch")
        if value.get("request_id") != expected_request_id:
            raise WorkerProtocolError("worker response request id mismatch")
        return WorkerResponse(
            request_id=value["request_id"],
            ok=bool(value["ok"]),
            value=value.get("value"),
            error_code=value.get("error_code"),
            error=value.get("error"),
        )
    except WorkerProtocolError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise WorkerProtocolError("worker returned malformed JSON response") from exc


def execute_snapshot(request: WorkerRequest) -> WorkerResponse:
    if request.protocol_version != PROTOCOL_VERSION:
        raise WorkerProtocolError("worker protocol version mismatch")
    try:
        with open(request.snapshot_path, "rb") as source_file:  # noqa: PTH123
            source_bytes = source_file.read()
        actual_hash = hashlib.sha256(source_bytes).hexdigest()
        if actual_hash != request.expected_source_hash:
            raise WorkerProtocolError("snapshot content hash mismatch")
        namespace = {
            "__name__": "__rpa_worker__",
            "__file__": request.snapshot_path,
        }
        exec(compile(source_bytes, request.snapshot_path, "exec"), namespace)  # noqa: S102
        entry = namespace.get("main") or namespace.get("run")
        if not callable(entry):
            raise WorkerProtocolError("snapshot must define callable main(payload)")
        value = entry(dict(request.payload))
        json.dumps(value)
        return WorkerResponse(request.request_id, True, value=value)
    except WorkerProtocolError:
        raise
    except Exception as exc:
        return WorkerResponse(
            request.request_id,
            False,
            error_code="automation_worker_failed",
            error=f"{type(exc).__name__}: {exc}",
        )


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not args.worker:
        return 2
    for line in sys.stdin:
        try:
            raw = json.loads(line)
            request = WorkerRequest(
                request_id=str(raw["request_id"]),
                snapshot_path=str(raw["snapshot_path"]),
                expected_source_hash=str(raw["expected_source_hash"]),
                payload=dict(raw.get("payload") or {}),
                protocol_version=str(raw.get("protocol_version", "")),
            )
            response = execute_snapshot(request)
        except Exception as exc:
            request_id = (
                str(raw.get("request_id", "unknown")) if isinstance(raw, dict) else "unknown"
            )
            response = WorkerResponse(
                request_id,
                False,
                error_code=getattr(exc, "code", "automation_worker_protocol_error"),
                error=str(exc),
            )
        sys.stdout.write(json.dumps(response.to_dict(), sort_keys=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
