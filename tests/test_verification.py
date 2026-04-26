"""Tests for verification contracts."""
from harness.verification import (
    CheckType,
    SuccessCheck,
    VerificationResult,
    validate_workflow,
    validate_workflow_step,
    CheckRunner,
)


def test_check_type_enum():
    assert CheckType.URL_CONTAINS == "url_contains"
    assert CheckType.STATUS_CODE == "status_code"
    assert CheckType.FILE_EXISTS == "file_exists"


def test_success_check_from_dict():
    check = SuccessCheck.from_dict({"type": "url_contains", "value": "/dashboard"})
    assert check.type == CheckType.URL_CONTAINS
    assert check.value == "/dashboard"
    assert check.redacted is False


def test_success_check_redacted():
    check = SuccessCheck.from_dict({"type": "field_has_value", "value": "", "redacted": True})
    assert check.type == CheckType.FIELD_HAS_VALUE
    assert check.redacted is True


def test_validate_step_missing_check():
    errors = validate_workflow_step({"id": "test", "action": {"type": "browser.click"}})
    assert len(errors) == 1
    assert "missing success_check" in errors[0]


def test_validate_step_no_op_allowed():
    errors = validate_workflow_step({
        "id": "test",
        "action": {"type": "no_op"},
        "allow_without_success_check": True,
    })
    assert len(errors) == 0


def test_validate_step_bad_check_type():
    errors = validate_workflow_step({
        "id": "test",
        "action": {"type": "browser.click"},
        "success_check": [{"type": "invalid_check_type"}],
    })
    assert len(errors) == 1


def test_validate_workflow_missing_fields():
    errors = validate_workflow({"id": "test"})
    assert len(errors) > 0


def test_validate_workflow_valid():
    wf = {
        "id": "test",
        "name": "Test",
        "version": "1.0",
        "type": "browser",
        "steps": [{
            "id": "s1",
            "action": {"type": "browser.goto", "url": "https://example.com"},
            "success_check": [{"type": "url_contains", "value": "example.com"}],
        }],
    }
    errors = validate_workflow(wf)
    assert len(errors) == 0


def test_check_runner_file_exists(tmp_path):
    import os
    f = tmp_path / "test.txt"
    f.write_text("hello")

    runner = CheckRunner()
    result = runner.run(SuccessCheck(type=CheckType.FILE_EXISTS, value=str(f)))
    assert result.passed

    result2 = runner.run(SuccessCheck(type=CheckType.FILE_EXISTS, value="/nonexistent/path"))
    assert not result2.passed


def test_check_runner_always_pass():
    runner = CheckRunner()
    result = runner.run(SuccessCheck(type=CheckType.ALWAYS_PASS))
    assert result.passed


def test_check_runner_text_contains():
    runner = CheckRunner()
    runner.set_context("last_text", "Hello World")
    result = runner.run(SuccessCheck(type=CheckType.TEXT_CONTAINS, value="World"))
    assert result.passed
    result2 = runner.run(SuccessCheck(type=CheckType.TEXT_CONTAINS, value="NotFound"))
    assert not result2.passed


def test_check_runner_url_contains():
    runner = CheckRunner()
    runner.set_context("current_url", "https://example.com/dashboard")
    result = runner.run(SuccessCheck(type=CheckType.URL_CONTAINS, value="/dashboard"))
    assert result.passed
    result2 = runner.run(SuccessCheck(type=CheckType.URL_CONTAINS, value="/login"))
    assert not result2.passed


def test_check_runner_variable_has_value():
    runner = CheckRunner()
    runner.set_context("title", "My Page")
    result = runner.run(SuccessCheck(type=CheckType.VARIABLE_HAS_VALUE, value="title"))
    assert result.passed
    result2 = runner.run(SuccessCheck(type=CheckType.VARIABLE_HAS_VALUE, value="empty_var"))
    assert not result2.passed


def test_check_runner_status_code():
    runner = CheckRunner()
    runner.set_context("status_code", 200)
    result = runner.run(SuccessCheck(type=CheckType.STATUS_CODE, value=200))
    assert result.passed
    result2 = runner.run(SuccessCheck(type=CheckType.STATUS_CODE, value=404))
    assert not result2.passed


def test_check_runner_redacted():
    runner = CheckRunner()
    runner.set_context("field_value", "secret123")
    result = runner.run(SuccessCheck(type=CheckType.FIELD_HAS_VALUE, redacted=True))
    assert result.passed
    assert result.evidence.get("redacted")
