"""
RPA Harness domain exception hierarchy.
Provides typed errors with error codes for classification and recovery.
"""

from typing import Any, Dict, Optional, Union


class RPAError(Exception):
    code: str = "UNKNOWN"
    category: str = "UNKNOWN"

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


class TimeoutError(RPAError):
    code = "TIMEOUT"
    category = "TRANSIENT"


class ElementNotFoundError(RPAError):
    code = "ELEMENT_NOT_FOUND"
    category = "TRANSIENT"


class ElementStaleError(RPAError):
    code = "ELEMENT_STALE"
    category = "TRANSIENT"


class SelectorInvalidError(RPAError):
    code = "SELECTOR_INVALID"
    category = "PERMANENT"


class ConnectionTimeoutError(RPAError):
    code = "CONNECTION_TIMEOUT"
    category = "TRANSIENT"


class NetworkError(RPAError):
    code = "NETWORK_ERROR"
    category = "TRANSIENT"


class AuthenticationError(RPAError):
    code = "AUTHENTICATION_ERROR"
    category = "PERMANENT"


class PermissionDeniedError(RPAError):
    code = "PERMISSION_DENIED"
    category = "PERMANENT"


class FileNotFoundError_(RPAError):
    code = "FILE_NOT_FOUND"
    category = "PERMANENT"


class ResourceLockedError(RPAError):
    code = "RESOURCE_LOCKED"
    category = "TRANSIENT"


class ConfigInvalidError(RPAError):
    code = "CONFIG_INVALID"
    category = "PERMANENT"


class ValidationError(RPAError):
    code = "VALIDATION_ERROR"
    category = "PERMANENT"


class WorkflowError(RPAError):
    code = "WORKFLOW_ERROR"
    category = "UNKNOWN"


class AgentError(RPAError):
    code = "AGENT_ERROR"
    category = "TRANSIENT"


class DriverError(RPAError):
    code = "DRIVER_ERROR"
    category = "UNKNOWN"


ERROR_CATEGORIES = {
    "TRANSIENT": "Temporary error — retryable (timeout, stale element, network, resource locked)",
    "PERMANENT": "Will not succeed with retry (invalid selector, permission denied, config error)",
    "UNKNOWN": "Unclassified — needs investigation",
}

RULEBOOK_FAILURE_CLASSES = {
    "transient": "Temporary condition that may succeed after a bounded retry",
    "data": "Input is missing, malformed, ambiguous, duplicated, or incompatible",
    "business": "Target system rejected the action for a valid business reason",
    "authorization_config": "Automation is not allowed or not configured to proceed",
    "automation_defect": "Workflow logic no longer matches target reality",
    "external_system": "Dependency is unavailable or contract-incompatible",
    "security_privacy": "Workflow risks leaking or mishandling sensitive data",
    "unknown": "Unclassified failure requiring evidence-first investigation",
}

_LEGACY_TO_RULEBOOK = {
    "TRANSIENT": "transient",
    "PERMANENT": "automation_defect",
    "UNKNOWN": "unknown",
}

_CODE_TO_RULEBOOK = {
    "TIMEOUT": "transient",
    "ELEMENT_STALE": "transient",
    "CONNECTION_TIMEOUT": "transient",
    "NETWORK_ERROR": "transient",
    "RESOURCE_LOCKED": "transient",
    "AGENT_ERROR": "transient",
    "AUTHENTICATION_ERROR": "authorization_config",
    "PERMISSION_DENIED": "authorization_config",
    "CONFIG_INVALID": "authorization_config",
    "VALIDATION_ERROR": "data",
    "FILE_NOT_FOUND": "data",
    "ELEMENT_NOT_FOUND": "automation_defect",
    "SELECTOR_INVALID": "automation_defect",
    "DRIVER_ERROR": "automation_defect",
    "WORKFLOW_ERROR": "unknown",
}

_CLASS_DEFAULTS = {
    "transient": {
        "recoverability": "recoverable",
        "retry_allowed": True,
        "side_effect_risk": "low",
        "human_review_required": False,
    },
    "data": {
        "recoverability": "record_recoverable",
        "retry_allowed": False,
        "side_effect_risk": "low",
        "human_review_required": True,
    },
    "business": {
        "recoverability": "not_retryable",
        "retry_allowed": False,
        "side_effect_risk": "medium",
        "human_review_required": True,
    },
    "authorization_config": {
        "recoverability": "configuration_required",
        "retry_allowed": False,
        "side_effect_risk": "medium",
        "human_review_required": True,
    },
    "automation_defect": {
        "recoverability": "repair_required",
        "retry_allowed": False,
        "side_effect_risk": "medium",
        "human_review_required": True,
    },
    "external_system": {
        "recoverability": "dependency_recoverable",
        "retry_allowed": False,
        "side_effect_risk": "medium",
        "human_review_required": True,
    },
    "security_privacy": {
        "recoverability": "must_stop",
        "retry_allowed": False,
        "side_effect_risk": "high",
        "human_review_required": True,
    },
    "unknown": {
        "recoverability": "unknown",
        "retry_allowed": False,
        "side_effect_risk": "unknown",
        "human_review_required": True,
    },
}


def classify_error(exception: Exception) -> str:
    if isinstance(exception, RPAError):
        return exception.category

    exc_str = str(exception).lower()
    if any(kw in exc_str for kw in ("timeout", "timed out", "wait")):
        return "TRANSIENT"
    if any(kw in exc_str for kw in ("connection", "network", "dns", "refused")):
        return "TRANSIENT"
    if any(kw in exc_str for kw in ("stale", "detached", "reload")):
        return "TRANSIENT"
    if any(kw in exc_str for kw in ("not found", "missing", "does not exist")):
        return "PERMANENT"
    if any(kw in exc_str for kw in ("permission", "access denied", "forbidden")):
        return "PERMANENT"

    return "UNKNOWN"


def classify_failure(
    error: Union[Exception, str],
    root_observation: Optional[str] = None,
) -> Dict[str, Any]:
    error_class = _classify_rulebook_error(error)
    classification = dict(_CLASS_DEFAULTS[error_class])
    classification["error_class"] = error_class
    classification["root_observation"] = root_observation or _extract_root_observation(error)
    classification["recommended_route"] = recommended_failure_route(classification)
    return classification


def recommended_failure_route(classification: Dict[str, Any]) -> str:
    error_class = str(classification.get("error_class") or "unknown")
    if error_class == "transient" and classification.get("retry_allowed"):
        return "retry"
    if error_class in {"data", "business"}:
        return "skip_or_needs_review"
    if error_class in {
        "authorization_config",
        "automation_defect",
        "external_system",
        "security_privacy",
    }:
        return "stop_and_escalate"
    return "stop_with_evidence"


def legacy_category_to_error_class(category: str) -> str:
    normalized = (category or "UNKNOWN").upper()
    return _LEGACY_TO_RULEBOOK.get(normalized, _normalize_rulebook_class(category))


def _classify_rulebook_error(error: Union[Exception, str]) -> str:
    if isinstance(error, RPAError):
        if error.details.get("error_class"):
            return _normalize_rulebook_class(str(error.details["error_class"]))
        if error.code in _CODE_TO_RULEBOOK:
            return _CODE_TO_RULEBOOK[error.code]
        return legacy_category_to_error_class(error.category)

    text = str(error).lower()
    if any(
        kw in text
        for kw in ("password", "token", "cookie", "secret", "private payload", "sensitive")
    ):
        return "security_privacy"
    if any(
        kw in text
        for kw in (
            "login denied",
            "mfa",
            "session expired",
            "credential",
            "unauthorized",
            "permission",
            "forbidden",
            "wrong tenant",
            "license",
            "feature flag",
        )
    ):
        return "authorization_config"
    if any(
        kw in text
        for kw in (
            "missing required",
            "malformed",
            "invalid date",
            "invalid amount",
            "invalid account",
            "invalid identifier",
            "duplicate input",
            "no matching",
            "too many matches",
            "file format",
            "schema expected",
        )
    ):
        return "data"
    if any(
        kw in text
        for kw in (
            "already exists",
            "account closed",
            "payment rejected",
            "approval required",
            "validation rule",
            "inventory unavailable",
            "business rule",
        )
    ):
        return "business"
    if any(
        kw in text
        for kw in (
            "selector",
            "element",
            "image marker",
            "branch condition",
            "loop index",
            "output port",
            "unexpected modal",
            "app version",
        )
    ):
        return "automation_defect"
    if any(
        kw in text
        for kw in (
            "5xx",
            "503",
            "502",
            "500",
            "database unavailable",
            "mailbox unavailable",
            "service unavailable",
            "response schema changed",
            "report format changed",
            "dependency down",
        )
    ):
        return "external_system"
    if any(
        kw in text
        for kw in (
            "timeout",
            "timed out",
            "wait",
            "network",
            "dns",
            "refused",
            "stale",
            "detached",
            "reload",
            "rate limit",
            "file lock",
            "busy",
            "clickability",
            "focus",
        )
    ):
        return "transient"
    if any(kw in text for kw in ("not found", "missing", "does not exist")):
        return "data"
    return "unknown"


def _normalize_rulebook_class(error_class: str) -> str:
    normalized = (error_class or "unknown").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "authorization": "authorization_config",
        "configuration": "authorization_config",
        "authorization_or_configuration": "authorization_config",
        "security": "security_privacy",
        "privacy": "security_privacy",
        "security_or_privacy": "security_privacy",
        "external": "external_system",
        "permanent": "automation_defect",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in RULEBOOK_FAILURE_CLASSES else "unknown"


def _extract_root_observation(error: Union[Exception, str]) -> Optional[str]:
    if isinstance(error, RPAError):
        for key in ("root_observation", "actual_result", "observed", "message"):
            value = error.details.get(key)
            if value:
                return str(value)
        return error.message
    observation = str(error)
    return observation or None
