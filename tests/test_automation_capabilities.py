"""Capability ports through the shared AutomationApplication seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    DuplicateWriteError,
    MappingSecretAdapter,
    SelectorEvidence,
    VerificationResult,
)
from harness.automation.capabilities import (
    ACTION_CLASSES,
    BROWSER_SELECTOR_PRIORITY,
    DESKTOP_SELECTOR_PRIORITY,
    CapabilityExecutor,
    CapabilityOp,
    FakeApi,
    FakeBrowser,
    FakeDesktop,
    FakeExcel,
    validate_selector_priority,
)


def proposal_for(definition, capability="browser"):
    return AutomationProposal(
        proposal_id=f"p-{definition.definition_id}",
        intent=AutomationIntent(
            intent_id=f"i-{definition.definition_id}",
            name=definition.name,
            objective=definition.success_check,
            required_capabilities=(capability,),
        ),
        discovery=DiscoveryEvidence(
            evidence_id=f"d-{definition.definition_id}",
            selectors=tuple(
                action.selector for action in definition.actions if action.selector is not None
            )
            or (SelectorEvidence("role", "main", True),),
            observed_capabilities=(capability,),
        ),
        definition=definition,
    )


def register(app, definition, capability="browser"):
    return app.register_proposal(proposal_for(definition, capability))


def grant(app, version):
    return app.grant_approval(
        definition_id=version.definition.definition_id,
        version=version.version,
        actor="operator@example",
        target_scope=version.definition.target_scope or "local",
        record_scope=version.definition.record_scope or "record-1",
        side_effect_scope=version.definition.side_effect_scope or "side-effect",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        action_id=version.definition.action_id,
    )


def test_capability_action_classes_are_declared():
    for name in (
        "navigate",
        "inspect",
        "extract",
        "fill",
        "click",
        "wait",
        "download",
        "screenshot",
        "api_get",
        "api_post",
        "excel_read",
        "excel_write",
        "desktop_launch",
        "desktop_click",
        "desktop_type",
    ):
        assert name in ACTION_CLASSES
        assert ACTION_CLASSES[name] in {"R0", "R1", "R2", "R3", "R4"}


def test_selector_priority_ladders_and_weak_fallbacks():
    assert BROWSER_SELECTOR_PRIORITY[0] == "role"
    assert DESKTOP_SELECTOR_PRIORITY[0] == "automation_id"
    validate_selector_priority(SelectorEvidence("role", "Save", True), surface="browser")
    with pytest.raises(ValueError, match="weak selector"):
        validate_selector_priority(SelectorEvidence("xpath", "//x", False), surface="browser")


def test_browser_read_write_verification_failure_and_repair_fixture():
    app = AutomationApplication(store=InMemoryEventStore())
    browser = FakeBrowser()
    executor = CapabilityExecutor(browser=browser)

    read_def = AutomationDefinition(
        definition_id="browser-read",
        name="Extract count",
        success_check="count text present",
        action_id="extract",
        actions=(
            AutomationAction(
                "extract",
                "browser",
                "R0",
                "count text present",
                selector=SelectorEvidence("role", "count", True),
            ),
        ),
    )
    register(app, read_def)
    read = app.execute_read_only(
        "browser-read",
        executor.as_read_adapter(
            CapabilityOp(
                "extract",
                "R0",
                True,
                selector=SelectorEvidence("role", "count", True),
                success_check="count text present",
            )
        ),
        lambda result: VerificationResult(
            passed="count" in str(result.value.get("text", "")),
            message="url/field/business evidence",
            evidence={"url": browser.pages.get("url"), "field_state": result.value},
        ),
    )
    assert read.status == "completed"
    assert "dom" in str(read.evidence_references) or read.evidence_references

    write_def = AutomationDefinition(
        definition_id="browser-write",
        name="Fill form",
        success_check="field filled",
        action_id="fill",
        action_class="R3",
        read_only=False,
        target_scope="demo-form",
        record_scope="form-1",
        side_effect_scope="form.field",
        idempotency_scope="browser-write:form-1",
        credential_names=("api_token",),
        actions=(
            AutomationAction(
                "fill",
                "browser",
                "R3",
                "field filled",
                selector=SelectorEvidence("label", "Name", True),
                credential_names=("api_token",),
                inputs={"value": "${secrets.api_token}"},
            ),
        ),
    )
    version = register(app, write_def)
    g = grant(app, version)
    write = app.execute_write(
        "browser-write",
        version=version.version,
        grant_id=g.grant_id,
        adapter=executor.as_write_adapter(
            CapabilityOp(
                "fill",
                "R3",
                False,
                inputs={"value": "${secrets.api_token}"},
                selector=SelectorEvidence("label", "Name", True),
            )
        ),
        verify=lambda result: VerificationResult(
            passed=result.value.get("filled") is True, message="field state ok"
        ),
        actor="operator@example",
        secret_adapter=MappingSecretAdapter({"api_token": "secret-value"}),
    )
    assert write.status == "completed"
    assert browser.writes
    assert "secret-value" not in str(write.to_dict())

    # Verification failure path
    browser.pages["field"] = "bad"
    fail_def = AutomationDefinition(
        definition_id="browser-fail",
        name="Extract fail",
        success_check="expected text",
        actions=(
            AutomationAction(
                "extract",
                "browser",
                "R0",
                "expected text",
                selector=SelectorEvidence("role", "count", True),
            ),
        ),
    )
    register(app, fail_def)
    failed = app.execute_read_only(
        "browser-fail",
        executor.as_read_adapter(
            CapabilityOp(
                "extract",
                "R0",
                True,
                selector=SelectorEvidence("role", "count", True),
            )
        ),
        lambda result: VerificationResult(
            passed=False, message="mismatch", failure_kind="verification_failed"
        ),
    )
    assert failed.status == "failed"

    # Selector repair path
    repair = app.propose_repair(
        parent_definition_id="browser-fail",
        parent_version=1,
        failure_run_id=failed.run_id,
        failure_kind="verification_failed",
        discovery=DiscoveryEvidence(
            evidence_id="repair-disc",
            selectors=(SelectorEvidence("role", "inventory count", True),),
            observed_capabilities=("browser",),
        ),
        proposed_definition=AutomationDefinition(
            definition_id="browser-fail",
            name="Extract fail",
            success_check="expected text",
            actions=(
                AutomationAction(
                    "extract",
                    "browser",
                    "R0",
                    "expected text",
                    selector=SelectorEvidence("role", "inventory count", True),
                ),
            ),
        ),
    )
    trial = app.trial_repair(
        repair.repair_id,
        adapter=executor.as_read_adapter(
            CapabilityOp(
                "extract",
                "R0",
                True,
                selector=SelectorEvidence("role", "inventory count", True),
            )
        ),
        verify=lambda result: VerificationResult(passed=True, message="repaired"),
    )
    assert trial.status == "passed"

    with pytest.raises(DuplicateWriteError):
        app.execute_write(
            "browser-write",
            version=version.version,
            grant_id=g.grant_id,
            adapter=executor.as_write_adapter(
                CapabilityOp(
                    "fill",
                    "R3",
                    False,
                    inputs={"value": "x"},
                    selector=SelectorEvidence("label", "Name", True),
                )
            ),
            verify=lambda result: VerificationResult(passed=True),
            actor="operator@example",
            secret_adapter=MappingSecretAdapter({"api_token": "secret-value"}),
        )
    assert len(browser.writes) == 1


def test_api_excel_desktop_capability_contracts():
    app = AutomationApplication(store=InMemoryEventStore())
    api, excel, desktop = FakeApi(), FakeExcel(), FakeDesktop()
    executor = CapabilityExecutor(api=api, excel=excel, desktop=desktop)

    api_def = AutomationDefinition(
        definition_id="api-read",
        name="API get",
        success_check="status 200",
        actions=(AutomationAction("api_get", "api", "R0", "status 200"),),
    )
    register(app, api_def, "api")
    api_summary = app.execute_read_only(
        "api-read",
        executor.as_read_adapter(
            CapabilityOp("api_get", "R0", True, inputs={"url": "https://example.test/items"})
        ),
        lambda result: VerificationResult(passed=result.value.get("status") == 200),
    )
    assert api_summary.status == "completed"
    assert api.calls

    excel_def = AutomationDefinition(
        definition_id="excel-read",
        name="Excel read",
        success_check="rows present",
        actions=(AutomationAction("excel_read", "excel", "R0", "rows present"),),
    )
    register(app, excel_def, "excel")
    excel_summary = app.execute_read_only(
        "excel-read",
        executor.as_read_adapter(
            CapabilityOp(
                "excel_read",
                "R0",
                True,
                inputs={"path": "book.xlsx", "sheet": "Inventory"},
            )
        ),
        lambda result: VerificationResult(passed=bool(result.value.get("rows"))),
    )
    assert excel_summary.status == "completed"

    desktop_def = AutomationDefinition(
        definition_id="desktop-read",
        name="Desktop read",
        success_check="text present",
        actions=(
            AutomationAction(
                "desktop_read",
                "desktop",
                "R0",
                "text present",
                selector=SelectorEvidence("automation_id", "Status", True),
            ),
        ),
    )
    register(app, desktop_def, "desktop")
    desktop_summary = app.execute_read_only(
        "desktop-read",
        executor.as_read_adapter(
            CapabilityOp(
                "desktop_read",
                "R0",
                True,
                selector=SelectorEvidence("automation_id", "Status", True),
            )
        ),
        lambda result: VerificationResult(passed="text" in result.value),
    )
    assert desktop_summary.status == "completed"

    write_excel = AutomationDefinition(
        definition_id="excel-write",
        name="Excel write",
        success_check="rows written",
        action_id="excel_write",
        action_class="R3",
        read_only=False,
        target_scope="workbook",
        record_scope="sheet-1",
        side_effect_scope="excel.rows",
        idempotency_scope="excel-write:sheet-1",
        actions=(AutomationAction("excel_write", "excel", "R3", "rows written"),),
    )
    version = register(app, write_excel, "excel")
    g = grant(app, version)
    written = app.execute_write(
        "excel-write",
        version=version.version,
        grant_id=g.grant_id,
        adapter=executor.as_write_adapter(
            CapabilityOp(
                "excel_write",
                "R3",
                False,
                inputs={
                    "path": "book.xlsx",
                    "sheet": "Inventory",
                    "rows": [{"sku": "1", "qty": 9}],
                },
            )
        ),
        verify=lambda result: VerificationResult(passed=result.value.get("written") == 1),
        actor="operator@example",
    )
    assert written.status == "completed"
    assert excel.writes

    write_desktop = AutomationDefinition(
        definition_id="desktop-write",
        name="Desktop type",
        success_check="typed",
        action_id="desktop_type",
        action_class="R3",
        read_only=False,
        target_scope="notepad",
        record_scope="field-1",
        side_effect_scope="desktop.text",
        idempotency_scope="desktop-write:field-1",
        actions=(
            AutomationAction(
                "desktop_type",
                "desktop",
                "R3",
                "typed",
                selector=SelectorEvidence("name", "Editor", True),
            ),
        ),
    )
    dversion = register(app, write_desktop, "desktop")
    dg = grant(app, dversion)
    typed = app.execute_write(
        "desktop-write",
        version=dversion.version,
        grant_id=dg.grant_id,
        adapter=executor.as_write_adapter(
            CapabilityOp(
                "desktop_type",
                "R3",
                False,
                inputs={"text": "hello"},
                selector=SelectorEvidence("name", "Editor", True),
            )
        ),
        verify=lambda result: VerificationResult(passed=result.value.get("typed") is True),
        actor="operator@example",
    )
    assert typed.status == "completed"
    assert desktop.writes
