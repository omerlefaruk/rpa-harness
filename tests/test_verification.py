"""Tests for verification contracts."""
import json

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
    assert any("missing success_check" in error for error in errors)
    assert any("requires selector" in error for error in errors)


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
    assert any("unknown type" in error for error in errors)


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


def test_validate_step_bad_json_path_payload():
    errors = validate_workflow_step({
        "id": "test",
        "action": {"type": "api.get"},
        "success_check": [{"type": "json_path_equals", "value": {"path": "$.id"}}],
    })
    assert any("value.path and value.value" in error for error in errors)


def test_validate_step_bad_cell_equals_payload():
    errors = validate_workflow_step({
        "id": "test",
        "action": {"type": "no_op"},
        "success_check": [{"type": "cell_equals", "value": {"cell": "A1"}}],
    })
    assert len(errors) == 1
    assert "value.cell and value.value" in errors[0]


def test_check_runner_download_exists(tmp_path):
    runner = CheckRunner()
    report = tmp_path / "report.pdf"
    report.write_text("ok")
    runner.set_context("downloaded_files", [str(report)])

    result = runner.run(SuccessCheck(type=CheckType.DOWNLOAD_EXISTS, value="report.pdf"))
    assert result.passed

    missing = runner.run(SuccessCheck(type=CheckType.DOWNLOAD_EXISTS, value="missing.pdf"))
    assert not missing.passed


def test_check_runner_json_path_equals():
    runner = CheckRunner()
    runner.set_context("response_body", json.dumps({"id": 1, "user": {"name": "Rau"}}))

    result = runner.run(
        SuccessCheck(
            type=CheckType.JSON_PATH_EQUALS,
            value={"path": "$.user.name", "value": "Rau"},
        )
    )
    assert result.passed

    missing = runner.run(
        SuccessCheck(
            type=CheckType.JSON_PATH_EQUALS,
            value={"path": "$.user.id", "value": "1"},
        )
    )
    assert not missing.passed


def test_check_runner_json_path_equals_supports_parser_features():
    runner = CheckRunner()
    runner.set_context(
        "response_json",
        {
            "items": [
                {"name": "alpha", "id": 1},
                {"name": "beta", "id": 2},
            ],
            "meta": {"odd.key": "value"},
        },
    )

    wildcard = runner.run(
        SuccessCheck(
            type=CheckType.JSON_PATH_EQUALS,
            value={"path": "$.items[*].name", "value": ["alpha", "beta"]},
        )
    )
    filtered = runner.run(
        SuccessCheck(
            type=CheckType.JSON_PATH_EQUALS,
            value={"path": '$.items[?(@.name == "beta")].id', "value": 2},
        )
    )
    quoted_key = runner.run(
        SuccessCheck(
            type=CheckType.JSON_PATH_EQUALS,
            value={"path": "$['meta']['odd.key']", "value": "value"},
        )
    )

    assert wildcard.passed
    assert filtered.passed
    assert quoted_key.passed


def test_check_runner_sheet_exists():
    runner = CheckRunner()
    runner.set_context("sheet_names", ["Input", "Results"])

    result = runner.run(SuccessCheck(type=CheckType.SHEET_EXISTS, value="Results"))
    assert result.passed

    missing = runner.run(SuccessCheck(type=CheckType.SHEET_EXISTS, value="Archive"))
    assert not missing.passed


def test_check_runner_cell_equals():
    runner = CheckRunner()
    runner.set_context("sheet_name", "Results")
    runner.set_context("cell_values", {"Results!A1": "OK", "B2": 4})

    result = runner.run(SuccessCheck(type=CheckType.CELL_EQUALS, value={"cell": "A1", "value": "OK"}))
    assert result.passed

    mismatch = runner.run(SuccessCheck(type=CheckType.CELL_EQUALS, value={"cell": "B2", "value": 5}))
    assert not mismatch.passed


def test_check_runner_window_exists():
    runner = CheckRunner()
    runner.set_context("available_windows", ["Calculator", "Notepad"])

    result = runner.run(SuccessCheck(type=CheckType.WINDOW_EXISTS, value="Calculator"))
    assert result.passed

    missing = runner.run(SuccessCheck(type=CheckType.WINDOW_EXISTS, value="Paint"))
    assert not missing.passed


def test_check_runner_element_exists():
    runner = CheckRunner()
    runner.set_context("elements", [{"automation_id": "num2Button"}, {"automation_id": "equalButton"}])

    result = runner.run(
        SuccessCheck(
            type=CheckType.ELEMENT_EXISTS,
            selector={"strategy": "automation_id", "value": "num2Button"},
        )
    )
    assert result.passed

    missing = runner.run(
        SuccessCheck(
            type=CheckType.ELEMENT_EXISTS,
            selector={"strategy": "automation_id", "value": "missingButton"},
        )
    )
    assert not missing.passed


def test_check_runner_element_text_equals():
    runner = CheckRunner()
    runner.set_context("element_text", "4")

    result = runner.run(SuccessCheck(type=CheckType.ELEMENT_TEXT_EQUALS, value="4"))
    assert result.passed

    mismatch = runner.run(SuccessCheck(type=CheckType.ELEMENT_TEXT_EQUALS, value="5"))
    assert not mismatch.passed
