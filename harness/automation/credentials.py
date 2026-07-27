"""Handle-only credential lifecycle at the local execution edge."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from harness.security import REDACTED, SecretValue, redact_value


class CredentialBackend(Protocol):
    def create(self, name: str, value: str) -> str: ...
    def update(self, name: str, value: str) -> str: ...
    def resolve(self, name_or_handle: str) -> SecretValue: ...
    def rotate(self, name: str, value: str) -> str: ...
    def delete(self, name: str) -> None: ...


@dataclass
class InMemoryCredentialBackend:
    """Test double for Windows Credential Manager semantics."""

    secrets: dict[str, str] = field(default_factory=dict)
    handles: dict[str, str] = field(default_factory=dict)

    def create(self, name: str, value: str) -> str:
        if name in self.secrets:
            raise ValueError(f"credential exists: {name}")
        handle = f"cred://{name}/{uuid4().hex[:8]}"
        self.secrets[name] = value
        self.handles[handle] = name
        return handle

    def update(self, name: str, value: str) -> str:
        if name not in self.secrets:
            raise KeyError(name)
        self.secrets[name] = value
        handle = f"cred://{name}/{uuid4().hex[:8]}"
        self.handles[handle] = name
        return handle

    def resolve(self, name_or_handle: str) -> SecretValue:
        name = self.handles.get(name_or_handle, name_or_handle)
        if name_or_handle.startswith("${secrets.") and name_or_handle.endswith("}"):
            name = name_or_handle[len("${secrets.") : -1]
        if name not in self.secrets:
            raise KeyError(f"missing credential: {name}")
        return SecretValue(name, self.secrets[name])

    def rotate(self, name: str, value: str) -> str:
        return self.update(name, value)

    def delete(self, name: str) -> None:
        self.secrets.pop(name, None)
        self.handles = {h: n for h, n in self.handles.items() if n != name}


@dataclass(frozen=True)
class CredentialAudit:
    operation: str
    name: str
    handle: str | None
    action_class: str
    actor: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return redact_value(asdict(self))


class CredentialService:
    """Agent-facing credential ops accept names/handles only; plaintext stays at the edge."""

    ACTION_CLASS = "R3"

    def __init__(self, backend: CredentialBackend, *, audit: list[CredentialAudit] | None = None) -> None:
        self._backend = backend
        self.audit = audit if audit is not None else []

    def create(self, name: str, plaintext: str, *, actor: str) -> dict[str, Any]:
        handle = self._backend.create(name, plaintext)
        self._record("create", name, handle, actor, "ok")
        return {"name": name, "handle": handle, "secret": REDACTED}

    def update(self, name: str, plaintext: str, *, actor: str) -> dict[str, Any]:
        handle = self._backend.update(name, plaintext)
        self._record("update", name, handle, actor, "ok")
        return {"name": name, "handle": handle, "secret": REDACTED}

    def resolve_handle(self, name_or_handle: str, *, actor: str) -> dict[str, Any]:
        """Agent-facing resolve returns name/handle metadata only, never plaintext."""

        secret = self._backend.resolve(name_or_handle)
        self._record("resolve", secret.name, name_or_handle, actor, "ok")
        return {"name": secret.name, "handle": name_or_handle, "secret": REDACTED}

    def resolve_edge(self, name_or_handle: str) -> SecretValue:
        """Local execution edge only."""

        return self._backend.resolve(name_or_handle)

    def rotate(self, name: str, plaintext: str, *, actor: str) -> dict[str, Any]:
        handle = self._backend.rotate(name, plaintext)
        self._record("rotate", name, handle, actor, "ok")
        return {"name": name, "handle": handle, "secret": REDACTED}

    def delete(self, name: str, *, actor: str) -> dict[str, Any]:
        self._backend.delete(name)
        self._record("delete", name, None, actor, "ok")
        return {"name": name, "deleted": True}

    def _record(
        self, operation: str, name: str, handle: str | None, actor: str, status: str
    ) -> None:
        self.audit.append(
            CredentialAudit(
                operation=operation,
                name=name,
                handle=handle,
                action_class=self.ACTION_CLASS,
                actor=actor,
                status=status,
                detail=datetime.now(UTC).isoformat(),
            )
        )
