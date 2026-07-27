"""Bounded repair trial, promote, and reject through the application seam."""

from __future__ import annotations

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    DiscoveryEvidence,
    RepairError,
    RunBudget,
    SelectorEvidence,
    ToolResult,
    VerificationResult,
)


def parent_def(**changes):
    values = {
        "definition_id": "form-read",
        "name": "Read form",
        "success_check": "value present",
        "action_id": "read-form",
        "actions": (
            AutomationAction(
                action_id="read-form",
                capability="read",
                action_class="R0",
                success_check="value present",
                selector=SelectorEvidence("css", "#old", True),
            ),
        ),
    }
    values.update(changes)
    return AutomationDefinition(**values)


def proposed_def(selector_strategy="role", locator="Save", verified=True):
    return AutomationDefinition(
        definition_id="form-read",
        name="Read form",
        success_check="value present",
        action_id="read-form",
        actions=(
            AutomationAction(
                action_id="read-form",
                capability="read",
                action_class="R0",
                success_check="value present",
                selector=SelectorEvidence(selector_strategy, locator, verified),
            ),
        ),
    )


def discovery(strategy="role", locator="Save", verified=True):
    return DiscoveryEvidence(
        evidence_id="disc_repair",
        selectors=(SelectorEvidence(strategy, locator, verified),),
        observed_capabilities=("read",),
    )


def register_parent(app):
    definition = parent_def()
    app.register_definition(definition)
    # Version via proposal-like direct register path: use register_proposal-compatible path
    from harness.automation import AutomationIntent, AutomationProposal

    proposal = AutomationProposal(
        proposal_id="p1",
        intent=AutomationIntent(
            intent_id="i1",
            name="Read form",
            objective="read",
            required_capabilities=("read",),
        ),
        discovery=discovery(strategy="css", locator="#old", verified=True),
        definition=definition,
    )
    return app.register_proposal(proposal)


def failure_run(app, definition_id="form-read"):
    return app.execute_read_only(
        definition_id,
        lambda _d, _r: ToolResult(value={}),
        lambda _result: VerificationResult(
            passed=False, message="selector failed", failure_kind="selector_failed"
        ),
    )


def test_successful_promotion_creates_new_version_preserving_parent():
    app = AutomationApplication(store=InMemoryEventStore())
    parent = register_parent(app)
    failed = failure_run(app)
    repair = app.propose_repair(
        parent_definition_id=parent.definition.definition_id,
        parent_version=parent.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=discovery(),
        proposed_definition=proposed_def(),
        rationale="prefer role over brittle css",
    )
    trial = app.trial_repair(
        repair.repair_id,
        adapter=lambda _d, _r: ToolResult(value={"value": "ok"}),
        verify=lambda result: VerificationResult(
            passed="value" in result.value, message="ok"
        ),
    )
    assert trial.status == "passed"
    assert trial.parent_diff["content_hash_parent"] != trial.parent_diff["content_hash_proposed"]

    promoted = app.promote_repair(repair.repair_id, trial_id=trial.trial_id)
    versions = app.definition_versions("form-read")
    assert len(versions) == 2
    assert versions[0].version == 1
    assert versions[0].content_hash == parent.content_hash
    assert promoted.version == 2
    assert promoted.content_hash == versions[1].content_hash


def test_failed_trial_does_not_promote():
    app = AutomationApplication(store=InMemoryEventStore())
    parent = register_parent(app)
    failed = failure_run(app)
    repair = app.propose_repair(
        parent_definition_id=parent.definition.definition_id,
        parent_version=parent.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=discovery(),
        proposed_definition=proposed_def(),
    )
    trial = app.trial_repair(
        repair.repair_id,
        adapter=lambda _d, _r: ToolResult(value={}),
        verify=lambda _r: VerificationResult(
            passed=False, message="still broken", failure_kind="verification_failed"
        ),
    )
    assert trial.status == "failed"
    with pytest.raises(RepairError, match="passing verification"):
        app.promote_repair(repair.repair_id, trial_id=trial.trial_id)
    assert len(app.definition_versions("form-read")) == 1


def test_exhausted_repair_budget():
    app = AutomationApplication(store=InMemoryEventStore())
    parent = register_parent(app)
    failed = failure_run(app)
    repair = app.propose_repair(
        parent_definition_id=parent.definition.definition_id,
        parent_version=parent.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=discovery(),
        proposed_definition=proposed_def(),
    )
    budget = RunBudget(max_repair_trials=1, max_tool_calls=2, max_action_attempts=2)
    first = app.trial_repair(
        repair.repair_id,
        adapter=lambda _d, _r: ToolResult(value={"value": "ok"}),
        verify=lambda result: VerificationResult(passed=True, message="ok"),
        budget=budget,
    )
    assert first.status == "passed"
    second = app.trial_repair(
        repair.repair_id,
        adapter=lambda _d, _r: ToolResult(value={"value": "ok"}),
        verify=lambda result: VerificationResult(passed=True, message="ok"),
        budget=budget,
    )
    assert second.status == "failed"
    assert second.failure_kind == "budget_exhausted"


def test_stale_parent_conflict_blocks_promotion():
    app = AutomationApplication(store=InMemoryEventStore())
    parent = register_parent(app)
    failed = failure_run(app)
    repair = app.propose_repair(
        parent_definition_id=parent.definition.definition_id,
        parent_version=parent.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=discovery(),
        proposed_definition=proposed_def(),
    )
    trial = app.trial_repair(
        repair.repair_id,
        adapter=lambda _d, _r: ToolResult(value={"value": "ok"}),
        verify=lambda result: VerificationResult(passed=True, message="ok"),
    )
    # Register a competing newer parent version before promote.
    from harness.automation import AutomationIntent, AutomationProposal

    competing = AutomationProposal(
        proposal_id="p2",
        intent=AutomationIntent(
            intent_id="i2",
            name="Read form",
            objective="read",
            required_capabilities=("read",),
        ),
        discovery=discovery(strategy="label", locator="Form", verified=True),
        definition=proposed_def(selector_strategy="label", locator="Form"),
    )
    app.register_proposal(competing)
    with pytest.raises(RepairError, match="stale parent"):
        app.promote_repair(repair.repair_id, trial_id=trial.trial_id)


def test_rejected_weak_selector_and_explicit_reject_leave_parent():
    app = AutomationApplication(store=InMemoryEventStore())
    parent = register_parent(app)
    failed = failure_run(app)
    with pytest.raises(RepairError, match="weak selector"):
        app.propose_repair(
            parent_definition_id=parent.definition.definition_id,
            parent_version=parent.version,
            failure_run_id=failed.run_id,
            failure_kind="selector_failed",
            discovery=discovery(strategy="xpath", locator="//x", verified=False),
            proposed_definition=proposed_def(
                selector_strategy="xpath", locator="//x", verified=False
            ),
        )

    repair = app.propose_repair(
        parent_definition_id=parent.definition.definition_id,
        parent_version=parent.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=discovery(),
        proposed_definition=proposed_def(),
    )
    app.reject_repair(repair.repair_id, reason="operator prefers manual fix")
    assert len(app.definition_versions("form-read")) == 1
    assert app.definition_versions("form-read")[0].content_hash == parent.content_hash


def test_replay_uses_cache_and_never_calls_adapter():
    app = AutomationApplication(store=InMemoryEventStore())
    parent = register_parent(app)
    failed = failure_run(app)
    repair = app.propose_repair(
        parent_definition_id=parent.definition.definition_id,
        parent_version=parent.version,
        failure_run_id=failed.run_id,
        failure_kind="selector_failed",
        discovery=discovery(),
        proposed_definition=proposed_def(),
    )
    calls = {"n": 0}

    def adapter(_d, _r):
        calls["n"] += 1
        return ToolResult(value={"value": "ok"})

    budget = RunBudget(max_repair_trials=2, max_tool_calls=3, max_action_attempts=2)
    first = app.trial_repair(
        repair.repair_id,
        adapter=adapter,
        verify=lambda result: VerificationResult(passed=True, message="ok"),
        budget=budget,
    )
    assert calls["n"] == 1
    cache_key = f"{repair.repair_id}:{parent.content_hash}"
    second = app.trial_repair(
        repair.repair_id,
        adapter=adapter,
        verify=lambda result: VerificationResult(passed=True, message="ok"),
        replay_cache={cache_key: ToolResult(value={"value": "cached"})},
        budget=budget,
    )
    assert calls["n"] == 1
    assert second.status == "passed"
    assert first.trial_id != second.trial_id
