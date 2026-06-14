"""Tests for RPA workflow rulebook audits."""

from harness.core import FailureClass, action_has_side_effect, audit_workflow_rulebook


def _complete_workflow():
    return {
        "owner": "ops",
        "target_systems": ["erp"],
        "input_schema": {"invoice_id": "str"},
        "system_of_record": "erp",
        "success_condition": "invoice status is exported in ERP",
        "safe_test_case": "test invoice INV-001",
        "allowed_side_effects": ["export_file"],
        "rerun_policy": "bounded rerun after checking external reference id",
        "escalation_owner": "ops-lead",
        "steps": [
            {
                "current_stage": "verify_export_file",
                "intent": "confirm invoice export completed",
                "preconditions": ["invoice id exists"],
                "postconditions": ["export file exists and is non-empty"],
                "proof": "export artifact metadata",
                "failure_path": "mark item needs_review and notify ops",
            }
        ],
    }


def test_failure_class_values_match_rulebook():
    assert [failure.value for failure in FailureClass] == [
        "transient",
        "data",
        "business",
        "authorization_config",
        "automation_defect",
        "external_system",
        "security_privacy",
        "unknown",
    ]


def test_audit_complete_rulebook_contract_scores_five():
    result = audit_workflow_rulebook(_complete_workflow())

    assert result.score == 5
    assert result.warnings == []
    assert result.missing_fields == []
    assert result.ready_for_unattended_production is True
    assert result.to_dict()["score"] == 5


def test_audit_missing_fields_are_warnings_not_exceptions():
    result = audit_workflow_rulebook(
        {"name": "legacy workflow", "steps": [{"action": {"type": "no_op"}}]}
    )

    assert result.score < 5
    assert "workflow.owner" in result.missing_fields
    assert "steps[0].proof" in result.missing_fields
    assert any("missing rulebook field" in warning for warning in result.warnings)


def test_success_check_counts_as_legacy_postcondition():
    workflow = _complete_workflow()
    workflow["steps"][0].pop("postconditions")
    workflow["steps"][0]["success_check"] = [{"type": "file_exists", "path": "output.csv"}]

    result = audit_workflow_rulebook(workflow)

    assert result.score == 5
    assert "steps[0].postconditions" not in result.missing_fields


def test_side_effecting_retry_without_guard_is_unsafe():
    workflow = _complete_workflow()
    workflow["steps"][0].update(
        {
            "action": {"type": "api.post"},
            "failure_class": "transient",
            "retry_policy": {"max_attempts": 2},
        }
    )

    result = audit_workflow_rulebook(workflow)

    assert action_has_side_effect("api.post") is True
    assert any("unsafe retry policy" in warning for warning in result.warnings)


def test_side_effecting_retry_with_idempotency_guard_is_safe():
    workflow = _complete_workflow()
    workflow["steps"][0].update(
        {
            "action": {"type": "api.post"},
            "failure_class": "transient",
            "retry_policy": {"max_attempts": 2},
            "idempotency_key": "invoice_id",
        }
    )

    result = audit_workflow_rulebook(workflow)

    assert not any("unsafe retry policy" in warning for warning in result.warnings)
