"""
RPA Harness domain exception hierarchy.
Provides typed errors with error codes for classification and recovery.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class RPAError(Exception):
    code: str = "UNKNOWN"
    category: str = "UNKNOWN"

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, cause: Optional[Exception] = None):
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
