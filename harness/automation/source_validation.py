"""Fail-closed validation and identity calculation for ordinary Python automations."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

VALIDATOR_VERSION = "python-automation-validator-4"
_UNPINNED = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^]]+\])?\s*(?:$|[<>~=!] )")
_DYNAMIC_NAMES = {"eval", "exec", "compile", "__import__", "reload"}
_DYNAMIC_MODULES = {"importlib", "runpy"}
_DANGEROUS_REFERENCES = _DYNAMIC_NAMES | {
    "__builtins__",
    "breakpoint",
    "delattr",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
_DANGEROUS_ATTRIBUTE_SEGMENTS = {
    "__builtins__",
    "__dict__",
    "__globals__",
    "__subclasses__",
    "builtins",
    "cr_frame",
    "f_globals",
    "f_locals",
    "gi_frame",
    "modules",
    "os",
    "stderr",
    "stdin",
    "stdout",
    "subprocess",
    "sys",
    "tb_frame",
}
_SAFE_FUTURE_FEATURES = {"annotations"}
_PURE_IMPORTS = {
    "collections",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "fractions",
    "functools",
    "hashlib",
    "itertools",
    "json",
    "math",
    "operator",
    "re",
    "statistics",
    "typing",
}
_PURE_IMPORT_CALLS = {
    "collections.ChainMap",
    "collections.Counter",
    "collections.OrderedDict",
    "collections.defaultdict",
    "collections.deque",
    "collections.namedtuple",
    "dataclasses.asdict",
    "dataclasses.astuple",
    "dataclasses.dataclass",
    "dataclasses.field",
    "dataclasses.fields",
    "dataclasses.is_dataclass",
    "dataclasses.make_dataclass",
    "dataclasses.replace",
    "datetime.date",
    "datetime.date.fromisoformat",
    "datetime.datetime",
    "datetime.datetime.combine",
    "datetime.datetime.fromisoformat",
    "datetime.datetime.strptime",
    "datetime.time",
    "datetime.timedelta",
    "datetime.timezone",
    "decimal.Context",
    "decimal.Decimal",
    "decimal.getcontext",
    "decimal.localcontext",
    "enum.Enum",
    "enum.Flag",
    "enum.IntEnum",
    "enum.IntFlag",
    "enum.StrEnum",
    "enum.auto",
    "enum.unique",
    "fractions.Fraction",
    "functools.cache",
    "functools.cached_property",
    "functools.cmp_to_key",
    "functools.lru_cache",
    "functools.partial",
    "functools.reduce",
    "functools.singledispatch",
    "functools.wraps",
    "hashlib.blake2b",
    "hashlib.blake2s",
    "hashlib.md5",
    "hashlib.new",
    "hashlib.sha1",
    "hashlib.sha224",
    "hashlib.sha256",
    "hashlib.sha384",
    "hashlib.sha3_224",
    "hashlib.sha3_256",
    "hashlib.sha3_384",
    "hashlib.sha3_512",
    "hashlib.sha512",
    "itertools.accumulate",
    "itertools.chain",
    "itertools.combinations",
    "itertools.combinations_with_replacement",
    "itertools.compress",
    "itertools.count",
    "itertools.cycle",
    "itertools.dropwhile",
    "itertools.filterfalse",
    "itertools.groupby",
    "itertools.islice",
    "itertools.pairwise",
    "itertools.permutations",
    "itertools.product",
    "itertools.repeat",
    "itertools.starmap",
    "itertools.takewhile",
    "itertools.tee",
    "itertools.zip_longest",
    "json.dumps",
    "json.loads",
    "math.acos",
    "math.asin",
    "math.atan",
    "math.atan2",
    "math.ceil",
    "math.comb",
    "math.cos",
    "math.degrees",
    "math.dist",
    "math.exp",
    "math.factorial",
    "math.floor",
    "math.fsum",
    "math.gcd",
    "math.hypot",
    "math.isclose",
    "math.isfinite",
    "math.isinf",
    "math.isnan",
    "math.lcm",
    "math.log",
    "math.log10",
    "math.log2",
    "math.perm",
    "math.prod",
    "math.radians",
    "math.remainder",
    "math.sin",
    "math.sqrt",
    "math.tan",
    "math.trunc",
    "operator.itemgetter",
    "re.compile",
    "re.escape",
    "re.findall",
    "re.finditer",
    "re.fullmatch",
    "re.match",
    "re.search",
    "re.split",
    "re.sub",
    "re.subn",
    "statistics.fmean",
    "statistics.geometric_mean",
    "statistics.harmonic_mean",
    "statistics.mean",
    "statistics.median",
    "statistics.median_grouped",
    "statistics.median_high",
    "statistics.median_low",
    "statistics.mode",
    "statistics.multimode",
    "statistics.pstdev",
    "statistics.pvariance",
    "statistics.quantiles",
    "statistics.stdev",
    "statistics.variance",
    "typing.NamedTuple",
    "typing.NewType",
    "typing.TypedDict",
    "typing.cast",
    "typing.get_args",
    "typing.get_origin",
}
_POSITIONAL_CALLBACKS = {
    "filter": (0,),
    "map": (0,),
    "functools.reduce": (0,),
    "itertools.dropwhile": (0,),
    "itertools.filterfalse": (0,),
    "itertools.groupby": (1,),
    "itertools.starmap": (0,),
    "itertools.takewhile": (0,),
}
_KEYWORD_CALLBACKS = {
    "max": ("key",),
    "min": ("key",),
    "sorted": ("key",),
}
_SAFE_CALL_NAMES = {
    "abs",
    "action",
    "action_boundary",
    "all",
    "any",
    "bool",
    "check",
    "dict",
    "enumerate",
    "filter",
    "float",
    "int",
    "len",
    "list",
    "map",
    "max",
    "min",
    "observation",
    "observe",
    "range",
    "read",
    "reversed",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "verification",
    "verify",
    "write",
    "zip",
}
_SAFE_METHOD_NAMES = {
    "append",
    "casefold",
    "copy",
    "count",
    "endswith",
    "extend",
    "format",
    "get",
    "index",
    "items",
    "join",
    "keys",
    "lower",
    "lstrip",
    "pop",
    "removeprefix",
    "removesuffix",
    "rstrip",
    "setdefault",
    "sort",
    "split",
    "splitlines",
    "startswith",
    "strip",
    "title",
    "upper",
    "update",
    "values",
}
_SIDE_EFFECT_ATTRIBUTES = {
    "chmod",
    "click",
    "delete",
    "fill",
    "mkdir",
    "patch",
    "post",
    "put",
    "rename",
    "replace",
    "rmdir",
    "send",
    "symlink_to",
    "touch",
    "type_text",
    "unlink",
    "write_bytes",
    "write_text",
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
        return SourceValidation(
            False,
            (f"syntax error: {exc.msg}",),
            source_hash=source_hash,
            dependency_lock_hash=lock_hash,
        )

    capabilities: set[str] = set()
    resources: set[str] = set()
    writes = False
    imported_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                imported_aliases[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            root = (node.module or "").split(".", 1)[0]
            for alias in node.names:
                imported_aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
    local_callables = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    local_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    trusted_call_roots = local_callables | set(imported_aliases) | _SAFE_CALL_NAMES
    rebound_callables = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id in trusted_call_roots
    } | {
        node.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.arg) and node.arg in trusted_call_roots
    }
    safe_value_names = _safe_value_names(
        tree,
        imported_aliases=imported_aliases,
        local_classes=local_classes,
        rebound_callables=rebound_callables,
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _DANGEROUS_REFERENCES:
            errors.append(f"unsupported runtime namespace access: {node.id}")
        elif isinstance(node, ast.Attribute):
            name = _attribute_name(node)
            imported_reference = _normalized_import_call(name, imported_aliases)
            if any(segment in _DANGEROUS_ATTRIBUTE_SEGMENTS for segment in name.split(".")[1:]):
                errors.append(f"unsupported runtime attribute access: {name}")
            elif imported_reference is not None and any(
                segment in _DANGEROUS_ATTRIBUTE_SEGMENTS
                for segment in imported_reference.split(".")[1:]
            ):
                errors.append(f"unsupported imported runtime reference: {imported_reference}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                imported_aliases[alias.asname or root] = root
                if root in _DYNAMIC_MODULES:
                    errors.append(f"unsupported dynamic loading: {root}")
                elif root not in _PURE_IMPORTS:
                    errors.append(f"unsupported or unanalyzed import: {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root == "__future__":
                unsupported = {
                    alias.name for alias in node.names if alias.name not in _SAFE_FUTURE_FEATURES
                }
                errors.extend(
                    f"unsupported future feature: {feature}" for feature in sorted(unsupported)
                )
                continue
            for alias in node.names:
                imported_aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
            if root in _DYNAMIC_MODULES:
                errors.append(f"unsupported dynamic loading: {root}")
            elif root not in _PURE_IMPORTS:
                errors.append(f"unsupported or unanalyzed import: {root}")
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            root = name.split(".", 1)[0] if name else ""
            leaf = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else (name.rsplit(".", 1)[-1] if name else "")
            )
            imported_call = _normalized_import_call(name, imported_aliases)
            normalized_call = imported_call or name
            if root in rebound_callables:
                errors.append(f"unsupported rebound call target: {root}")
            elif name in _DYNAMIC_NAMES:
                errors.append(f"unsupported dynamic loading: {name}")
            elif imported_call is not None and imported_call not in _PURE_IMPORT_CALLS:
                errors.append(f"unsupported or unanalyzed imported call: {imported_call}")
            elif imported_call is None and (
                not name
                or (
                    not (name in local_callables and "." not in name)
                    and name not in _SAFE_CALL_NAMES
                    and not (
                        "." in name and root in safe_value_names and leaf in _SAFE_METHOD_NAMES
                    )
                    and leaf not in _SIDE_EFFECT_ATTRIBUTES
                )
            ):
                errors.append(f"unsupported or unanalyzed call: {name or '<indirect>'}")
            for position in _POSITIONAL_CALLBACKS.get(normalized_call, ()):
                if position < len(node.args) and not _is_safe_callable_reference(
                    node.args[position],
                    local_callables=local_callables,
                    imported_aliases=imported_aliases,
                    rebound_callables=rebound_callables,
                ):
                    errors.append(f"unsupported callback for higher-order call: {normalized_call}")
            callback_keywords = _KEYWORD_CALLBACKS.get(normalized_call, ())
            for keyword in node.keywords:
                if keyword.arg in callback_keywords and not _is_safe_callable_reference(
                    keyword.value,
                    local_callables=local_callables,
                    imported_aliases=imported_aliases,
                    rebound_callables=rebound_callables,
                ):
                    errors.append(f"unsupported callback for higher-order call: {normalized_call}")
            if name in {"observe", "observation", "read"}:
                capabilities.add("read")
            if name in {"action", "write", "action_boundary"}:
                capabilities.add("write")
                writes = True
            if leaf in _SIDE_EFFECT_ATTRIBUTES:
                writes = True
                resources.add(name)
            if leaf in {"open", "request", "get", "head"}:
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
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _call_name(node: ast.Call) -> str:
    return _attribute_name(node.func)


def _attribute_name(node: ast.AST) -> str:
    value = node
    parts: list[str] = []
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if not isinstance(value, ast.Name):
        return ""
    parts.append(value.id)
    return ".".join(reversed(parts))


def _normalized_import_call(name: str, imported_aliases: dict[str, str]) -> str | None:
    if not name:
        return None
    root, separator, remainder = name.partition(".")
    imported = imported_aliases.get(root)
    if imported is None:
        return None
    return f"{imported}.{remainder}" if separator else imported


def _is_safe_callable_reference(
    node: ast.AST,
    *,
    local_callables: set[str],
    imported_aliases: dict[str, str],
    rebound_callables: set[str],
) -> bool:
    name = _attribute_name(node)
    if not name:
        return False
    root = name.split(".", 1)[0]
    if root in rebound_callables or root in _DANGEROUS_REFERENCES:
        return False
    imported = _normalized_import_call(name, imported_aliases)
    if imported is not None:
        return imported in _PURE_IMPORT_CALLS
    return name in local_callables or name in _SAFE_CALL_NAMES


def _safe_value_names(
    tree: ast.AST,
    *,
    imported_aliases: dict[str, str],
    local_classes: set[str],
    rebound_callables: set[str],
) -> set[str]:
    safe_names = {"payload"}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            target: ast.AST | None = None
            value: ast.AST | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            if (
                isinstance(target, ast.Name)
                and value is not None
                and target.id not in safe_names
                and _is_safe_value_expression(
                    value,
                    safe_names=safe_names,
                    imported_aliases=imported_aliases,
                    local_classes=local_classes,
                    rebound_callables=rebound_callables,
                )
            ):
                safe_names.add(target.id)
                changed = True
    return safe_names


def _is_safe_value_expression(
    node: ast.AST,
    *,
    safe_names: set[str],
    imported_aliases: dict[str, str],
    local_classes: set[str],
    rebound_callables: set[str],
) -> bool:
    if isinstance(node, (ast.Constant, ast.Dict, ast.List, ast.Set, ast.Tuple)):
        return True
    if isinstance(node, ast.Name):
        return node.id in safe_names
    if isinstance(node, ast.Subscript):
        return _is_safe_value_expression(
            node.value,
            safe_names=safe_names,
            imported_aliases=imported_aliases,
            local_classes=local_classes,
            rebound_callables=rebound_callables,
        )
    if not isinstance(node, ast.Call):
        return False
    name = _attribute_name(node.func)
    if not name:
        return False
    root = name.split(".", 1)[0]
    if root in rebound_callables:
        return False
    imported = _normalized_import_call(name, imported_aliases)
    if imported is not None:
        return imported in _PURE_IMPORT_CALLS
    if name in _SAFE_CALL_NAMES or name in local_classes:
        return True
    return "." in name and root in safe_names and name.rsplit(".", 1)[-1] in _SAFE_METHOD_NAMES


def _has_action_boundary(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and _call_name(node).rsplit(".", 1)[-1] in {"action", "action_boundary", "write"}
        for node in ast.walk(tree)
    )


def _has_verification(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and _call_name(node).rsplit(".", 1)[-1] in {"verify", "verification", "check"}
        for node in ast.walk(tree)
    )
