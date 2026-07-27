"""Typed, deterministic contracts for governed automation authoring."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from harness.security import SECRET_REF_RE, is_sensitive_key

CONTRACT_VERSION = "v1"
ALLOWED_CAPABILITIES = frozenset({"read", "write"})
ALLOWED_ACTION_CLASSES = frozenset({"R0", "R1", "R2", "R3", "R4"})
WRITE_ACTION_CLASSES = frozenset({"R1", "R2", "R3", "R4"})
WEAK_SELECTOR_STRATEGIES = frozenset({"css", "xpath", "coordinate"})
SECRET_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class AutomationIntent:
    intent_id: str
    name: str
    objective: str
    required_capabilities: tuple[str, ...]
    unresolved_business_ambiguities: tuple[str, ...] = ()
    schema_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class SelectorEvidence:
    strategy: str
    locator: str
    verified: bool


@dataclass(frozen=True)
class DiscoveryEvidence:
    evidence_id: str
    selectors: tuple[SelectorEvidence, ...]
    observed_capabilities: tuple[str, ...]
    schema_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class AutomationAction:
    action_id: str
    capability: str
    action_class: str
    success_check: str
    selector: SelectorEvidence | None = None
    credential_names: tuple[str, ...] = ()
    inputs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomationProposal:
    proposal_id: str
    intent: AutomationIntent
    discovery: DiscoveryEvidence
    definition: Any
    schema_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class DefinitionVersion:
    definition: Any
    version: int
    content_hash: str
    proposal_id: str
    schema_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProposalBudget:
    max_proposals: int = 1
    max_model_calls: int = 1


@dataclass(frozen=True)
class ProposalValidation:
    errors: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return not self.errors


class ProposalValidationError(ValueError):
    """Stable validation error suitable for equivalent transport responses."""

    code = "automation_proposal_invalid"

    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__(f"{self.code}: {'; '.join(errors)}")


class DiscoveryAdapter(Protocol):
    def discover(self, intent: AutomationIntent) -> DiscoveryEvidence: ...


class ProposalModelAdapter(Protocol):
    def propose(
        self, intent: AutomationIntent, discovery: DiscoveryEvidence
    ) -> AutomationProposal: ...


def validate_proposal(proposal: AutomationProposal) -> ProposalValidation:
    """Return all deterministic admission failures without invoking any driver."""

    errors: list[str] = []
    intent = proposal.intent
    definition = proposal.definition
    if proposal.schema_version != CONTRACT_VERSION:
        errors.append("unsupported proposal contract version")
    if (
        intent.schema_version != CONTRACT_VERSION
        or proposal.discovery.schema_version != CONTRACT_VERSION
    ):
        errors.append("unsupported intent or discovery contract version")
    if not intent.intent_id or not intent.name or not intent.objective:
        errors.append("intent requires id, name, and objective")
    if intent.unresolved_business_ambiguities:
        errors.append("unresolved business ambiguity")
    if not definition.definition_id or not definition.name or not definition.success_check:
        errors.append("definition requires id, name, and explicit success check")
    if definition.action_class not in ALLOWED_ACTION_CLASSES:
        errors.append("invalid action class")
    elif definition.read_only != (definition.action_class == "R0"):
        errors.append("invalid action class")
    capabilities = set(intent.required_capabilities)
    capabilities.update(proposal.discovery.observed_capabilities)
    if definition.actions:
        for action in definition.actions:
            capabilities.add(action.capability)
            if not action.success_check:
                errors.append("action missing explicit success check")
            if action.action_class not in ALLOWED_ACTION_CLASSES:
                errors.append("invalid action class")
            elif (action.capability == "write") != (action.action_class in WRITE_ACTION_CLASSES):
                errors.append("invalid action class")
            _validate_selector(action.selector, errors)
            _validate_secret_references(action.credential_names, action.inputs, errors)
    else:
        # Legacy single-action definitions encode the capability in action_id.
        capabilities.add(definition.action_id)
    if not definition.actions and not definition.success_check:
        errors.append("action missing explicit success check")
    for selector in proposal.discovery.selectors:
        _validate_selector(selector, errors)
    unknown = sorted(
        capability for capability in capabilities if capability not in ALLOWED_CAPABILITIES
    )
    if unknown:
        errors.append(f"unknown capabilities: {', '.join(unknown)}")
    return ProposalValidation(tuple(dict.fromkeys(errors)))


def content_hash(definition: Any) -> str:
    canonical = json.dumps(asdict(definition), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def proposal_from_dict(value: Mapping[str, Any], definition_type: type) -> AutomationProposal:
    """Parse an untrusted JSON proposal into contracts; values remain data, never tools."""

    intent_value = value["intent"]
    discovery_value = value["discovery"]
    definition_value = dict(value["definition"])
    definition_value["actions"] = tuple(
        _action_from_dict(item) for item in definition_value.get("actions", ())
    )
    definition = definition_type(**definition_value)
    return AutomationProposal(
        proposal_id=str(value["proposal_id"]),
        intent=AutomationIntent(
            intent_id=str(intent_value["intent_id"]),
            name=str(intent_value["name"]),
            objective=str(intent_value["objective"]),
            required_capabilities=tuple(intent_value.get("required_capabilities", ())),
            unresolved_business_ambiguities=tuple(
                intent_value.get("unresolved_business_ambiguities", ())
            ),
            schema_version=str(intent_value.get("schema_version", CONTRACT_VERSION)),
        ),
        discovery=DiscoveryEvidence(
            evidence_id=str(discovery_value["evidence_id"]),
            selectors=tuple(
                _selector_from_dict(item) for item in discovery_value.get("selectors", ())
            ),
            observed_capabilities=tuple(discovery_value.get("observed_capabilities", ())),
            schema_version=str(discovery_value.get("schema_version", CONTRACT_VERSION)),
        ),
        definition=definition,
        schema_version=str(value.get("schema_version", CONTRACT_VERSION)),
    )


def _action_from_dict(value: Mapping[str, Any]) -> AutomationAction:
    selector = value.get("selector")
    return AutomationAction(
        action_id=str(value["action_id"]),
        capability=str(value["capability"]),
        action_class=str(value["action_class"]),
        success_check=str(value["success_check"]),
        selector=_selector_from_dict(selector) if selector else None,
        credential_names=tuple(value.get("credential_names", ())),
        inputs=dict(value.get("inputs", {})),
    )


def _selector_from_dict(value: Mapping[str, Any]) -> SelectorEvidence:
    return SelectorEvidence(
        strategy=str(value["strategy"]),
        locator=str(value["locator"]),
        verified=bool(value["verified"]),
    )


def _validate_selector(selector: SelectorEvidence | None, errors: list[str]) -> None:
    if selector and selector.strategy in WEAK_SELECTOR_STRATEGIES and not selector.verified:
        errors.append("weak selector is not verified")


def _validate_secret_references(
    secret_names: tuple[str, ...], inputs: Mapping[str, Any], errors: list[str]
) -> None:
    if any(not SECRET_NAME_RE.fullmatch(name) for name in secret_names):
        errors.append("invalid secret name")
    for key, value in inputs.items():
        if is_sensitive_key(str(key)):
            if not isinstance(value, str) or not SECRET_REF_RE.fullmatch(value):
                errors.append("plaintext secrets are not accepted")
        elif _contains_plaintext_secret(value):
            errors.append("plaintext secrets are not accepted")


def _contains_plaintext_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            is_sensitive_key(str(key))
            and (not isinstance(item, str) or not SECRET_REF_RE.fullmatch(item))
            for key, item in value.items()
        ) or any(_contains_plaintext_secret(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_plaintext_secret(item) for item in value)
    return False
