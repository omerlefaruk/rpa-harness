"""Tests for deterministic redaction helpers."""

import json

from harness.security import REDACTED, SecretValue, redact_mapping, redact_text, sanitize_url


def test_sanitize_url_strips_query_and_fragment():
    assert sanitize_url("https://example.com/path?a=1#frag") == "https://example.com/path"


def test_redact_mapping_redacts_sensitive_keys():
    redacted = redact_mapping({"Authorization": "Bearer secret", "ok": "value"})
    assert redacted["Authorization"] == REDACTED
    assert redacted["ok"] == "value"


def test_redact_text_replaces_known_secret_values():
    assert redact_text("token is abc123", secret_values=["abc123"]) == f"token is {REDACTED}"


def test_redact_text_replaces_sensitive_assignments():
    assert redact_text("token=abc123") == f"token={REDACTED}"


def test_secret_value_does_not_stringify_or_json_serialize_raw_value():
    secret = SecretValue("api_token", "sk-test-canary-12345")

    assert str(secret) == REDACTED
    assert repr(secret) == REDACTED
    assert json.dumps({"token": secret}, default=str) == f'{{"token": "{REDACTED}"}}'
    assert secret.reveal() == "sk-test-canary-12345"
