"""Rulebook failure taxonomy classification tests."""

from harness.resilience.errors import (
    RULEBOOK_FAILURE_CLASSES,
    AuthenticationError,
    SelectorInvalidError,
    TimeoutError as RPATimeoutError,
    ValidationError,
    classify_error,
    classify_failure,
)


def test_rulebook_failure_classes_are_registered():
    assert set(RULEBOOK_FAILURE_CLASSES) == {
        "transient",
        "data",
        "business",
        "authorization_config",
        "automation_defect",
        "external_system",
        "security_privacy",
        "unknown",
    }


def test_legacy_classify_error_categories_are_preserved():
    assert classify_error(RPATimeoutError("Timed out")) == "TRANSIENT"
    assert classify_error(SelectorInvalidError("Selector is invalid")) == "PERMANENT"
    assert classify_error(Exception("unexpected failure")) == "UNKNOWN"


def test_structured_classification_for_rpa_errors():
    transient = classify_failure(
        RPATimeoutError(
            "Page timed out",
            details={"root_observation": "loading spinner remained visible"},
        )
    )
    assert transient == {
        "error_class": "transient",
        "recoverability": "recoverable",
        "retry_allowed": True,
        "side_effect_risk": "low",
        "human_review_required": False,
        "root_observation": "loading spinner remained visible",
        "recommended_route": "retry",
    }

    auth_config = classify_failure(AuthenticationError("Login denied"))
    assert auth_config["error_class"] == "authorization_config"
    assert auth_config["retry_allowed"] is False
    assert auth_config["human_review_required"] is True
    assert auth_config["recommended_route"] == "stop_and_escalate"

    data = classify_failure(ValidationError("Missing required account identifier"))
    assert data["error_class"] == "data"
    assert data["recoverability"] == "record_recoverable"


def test_structured_classification_for_rulebook_messages():
    assert classify_failure("Invoice already exists in target system")["error_class"] == "business"
    assert (
        classify_failure("API returned 503 service unavailable")["error_class"]
        == "external_system"
    )
    assert (
        classify_failure("Notification includes raw token value")["error_class"]
        == "security_privacy"
    )
    assert classify_failure("Something unexpected happened")["error_class"] == "unknown"
