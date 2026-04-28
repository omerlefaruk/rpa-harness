"""
Deterministic redaction and sanitization helpers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTED = "[REDACTED]"

SENSITIVE_KEY_PARTS = (
    "authorization",
    "api-key",
    "api_key",
    "apikey",
    "cookie",
    "password",
    "secret",
    "session",
    "set-cookie",
    "token",
)

AUTH_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9._~+/=-]+"),
)

SENSITIVE_ASSIGNMENT_PATTERNS = (
    re.compile(
        r"(?i)\b(token|password|secret|api[_-]?key|session|cookie)\s*([:=])\s*([^\s,;&\"'<>]+)"
    ),
)


def is_sensitive_key(key: str) -> bool:
    normalized = str(key).strip().lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def sanitize_url(url: str) -> str:
    value = str(url)
    parsed = urlsplit(value)
    if not parsed.scheme and not parsed.netloc:
        return urlunsplit(("", "", parsed.path, "", ""))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def redact_text(
    text: Any,
    secret_values: Iterable[str] | None = None,
    max_chars: int | None = None,
) -> str:
    value = str(text)
    for secret in secret_values or []:
        if secret:
            value = value.replace(str(secret), REDACTED)
    for pattern in AUTH_PATTERNS:
        value = pattern.sub(REDACTED, value)
    for pattern in SENSITIVE_ASSIGNMENT_PATTERNS:
        value = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value)
    if max_chars is not None and len(value) > max_chars:
        return value[:max_chars] + "...[truncated]"
    return value


def redact_value(
    value: Any,
    secret_values: Iterable[str] | None = None,
    max_chars: int | None = None,
) -> Any:
    if isinstance(value, str):
        return redact_text(value, secret_values=secret_values, max_chars=max_chars)
    if isinstance(value, list):
        return [
            redact_value(item, secret_values=secret_values, max_chars=max_chars) for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            redact_value(item, secret_values=secret_values, max_chars=max_chars) for item in value
        )
    if isinstance(value, dict):
        return redact_mapping(value, secret_values=secret_values, max_chars=max_chars)
    return value


def redact_mapping(
    mapping: Mapping[str, Any] | None,
    secret_values: Iterable[str] | None = None,
    max_chars: int | None = None,
) -> dict:
    redacted: dict[str, Any] = {}
    for key, value in (mapping or {}).items():
        if is_sensitive_key(str(key)):
            redacted[str(key)] = REDACTED
        else:
            redacted[str(key)] = redact_value(
                value,
                secret_values=secret_values,
                max_chars=max_chars,
            )
    return redacted


def redacted_preview(
    value: Any,
    secret_values: Iterable[str] | None = None,
    max_chars: int = 500,
) -> str:
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(redact_value(value, secret_values=secret_values), default=str)
    else:
        text = str(value)
    return redact_text(text, secret_values=secret_values, max_chars=max_chars)
