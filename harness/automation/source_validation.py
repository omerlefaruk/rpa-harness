"""Fail-closed validation and identity calculation for ordinary Python automations."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


VALIDATOR_VERSION = "python-automation-validator-1"
_UNPINNED = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^]]+\])?\s*(?:$|[<>~=!] )")
_DYNAMIC_NAMES = {"eval", "exec", "compile", "__import__", "reload"}
_DYNAMIC_MODULES = {"importlib", "runpy"}
_UNSAFE_IMPORTS = {"subprocess", "socket", "ctypes", "pyautogui"}
_SIDE_EFFECT_ATTRIBUTES = {
    "write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir",
    "send", "post", "put", "patch", "delete", "click", "fill", "type_text",
}


@dataclass(frozen=True)
class ActionManifest:
    action_class: str
    capabilities: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    writes: bool = False
    verification_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceValidation:
    accepted: bool
    errors: tuple[str, ...] = ()
    action_manifest: ActionManifest = field(
        default_factory=lambda: ActionManifest(action_class="R0")
    )
    source_hash: str = ""
    dependency_lock_hash: str = ""
    validator_version: str = VALIDATOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "errors": list(self.errors),
            "action_manifest": self.action_manifest.to_dict(),
            "source_hash": self.source_hash,
            "dependency_lock_hash": self.dependency_lock_hash,
            "validator_version": self.validator_version,
        }


class SourceValidationError(ValueError):
    code = "automation_source_invalid"

    def __init__(self, validation: SourceValidation) -> None:
        self.validation = validation
        super().__init__(f"{self.code}: {'; '.join(validation.errors)}")


def validate_source(
    source: str,
    *,
    dependency_lock: str = "",
    skill_hashes: tuple[str, ...] = (),
    declared_action_class: str = "R0",
) -> SourceValidation:
    """Validate source without importing or executing it.

    Unknown effects are deliberately rejected. Callers can explicitly route a
    reviewed exception through an operator-only override later.
    """

    errors: list[str] = []
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    lock_hash = hashlib.sha256(dependency_lock.encode("utf-8")).hexdigest()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return SourceValidation(False, (f"syntax error: {exc.msg}",), source_hash=source_hash, dependency_lock_hash=lock_hash)

    capabilities: set[str] = set()
    resources: set[str] = set()
    writes = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in _UNSAFE_IMPORTS:
                    errors.append(f"unsupported effect import: {root}")
                if root in _DYNAMIC_MODULES:
                    errors.append(f"unsupported dynamic loading: {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in _UNSAFE_IMPORTS:
                errors.append(f"unsupported effect import: {root}")
            if root in _DYNAMIC_MODULES:
                errors.append(f"unsupported dynamic loading: {root}")
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _DYNAMIC_NAMES:
                errors.append(f"unsupported dynamic loading: {name}")
            if name in {"observe", "observation", "read"}:
                capabilities.add("read")
            if name in {"action", "write", "action_boundary"}:
                capabilities.add("write")
                writes = True
            if name.rsplit(".", 1)[-1] in _SIDE_EFFECT_ATTRIBUTES:
                writes = True
                resources.add(name)
            if name.rsplit(".", 1)[-1] in {"open", "request", "get", "head"}:
                capabilities.add("read")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"SECRET", "TOKEN", "PASSWORD"}:
                    errors.append("credential values must be resolved through handles")

    if dependency_lock:
        for line in dependency_lock.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            if "==" not in stripped:
                errors.append(f"unpinned dependency: {stripped.split(';', 1)[0].strip()}")
    if writes and declared_action_class == "R0":
        errors.append("write effects require an R1-R4 Action Class")
    if declared_action_class not in {"R0", "R1", "R2", "R3", "R4"}:
        errors.append("missing or invalid Action Class")
    if writes and not _has_action_boundary(tree):
        errors.append("known write effect is outside an Action Boundary")
    if declared_action_class in {"R1", "R2", "R3", "R4"} and writes and not _has_verification(tree):
        errors.append("write-capable automation requires explicit Verification")

    manifest = ActionManifest(
        action_class=declared_action_class,
        capabilities=tuple(sorted(capabilities)),
        resources=tuple(sorted(resources)),
        writes=writes,
        verification_required=writes,
    )
    return SourceValidation(
        not errors,
        tuple(dict.fromkeys(errors)),
        manifest,
        source_hash,
        lock_hash,
    )


def revision_identity(
    source: str,
    dependency_lock: str,
    skill_hashes: tuple[str, ...],
    validation: SourceValidation,
) -> str:
    material = {
        "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "dependency_lock_hash": hashlib.sha256(dependency_lock.encode("utf-8")).hexdigest(),
        "skill_hashes": sorted(skill_hashes),
        "validator_version": validation.validator_version,
        "action_manifest": validation.action_manifest.to_dict(),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _call_name(node: ast.Call) -> str:
    value: ast.AST = node.func
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def _has_action_boundary(tree: ast.AST) -> bool:
    return any(isinstance(node, ast.Call) and _call_name(node).rsplit(".", 1)[-1] in {"action", "action_boundary", "write"} for node in ast.walk(tree))


def _has_verification(tree: ast.AST) -> bool:
    return any(isinstance(node, ast.Call) and _call_name(node).rsplit(".", 1)[-1] in {"verify", "verification", "check"} for node in ast.walk(tree))
