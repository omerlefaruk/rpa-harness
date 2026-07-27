"""Budgets, transition fingerprints, and spiral stops for autonomous runs."""

from __future__ import annotations

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AuthorityError,
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    BudgetExhaustedError,
    DiscoveryEvidence,
    ProposalBudget,
    RepeatedTransitionError,
    RunBudget,
    SelectorEvidence,
    ToolResult,
    VerificationResult,
)


def read_def():
    return AutomationDefinition(
        definition_id="inventory-read",
        name="Read inventory",
        success_check="inventory count is present",
    )


def intent(**changes):
    values = {
        "intent_id": "intent_1",
        "name": "Read inventory",
        "objective": "Return the inventory count",
        "required_capabilities": ("read",),
    }
    values.update(changes)
    return AutomationIntent(**values)


def discovery(selectors=None, **changes):
    values = {
        "evidence_id": "discovery_1",
        "selectors": selectors
        or (SelectorEvidence("role", "inventory count", True),),
        "observed_capabilities": ("read",),
    }
    values.update(changes)
    return DiscoveryEvidence(**values)


def proposal(for_intent=None, for_discovery=None, **definition_changes):
    definition = AutomationDefinition(
        definition_id="inventory-read",
        name="Read inventory",
        success_check="inventory count is present",
        actions=(
            AutomationAction(
                action_id="read-inventory",
                capability="read",
                action_class="R0",
                success_check="inventory count is present",
                selector=SelectorEvidence("role", "inventory count", True),
            ),
        ),
        **definition_changes,
    )
    return AutomationProposal(
        proposal_id="proposal_1",
        intent=for_intent or intent(),
        discovery=for_discovery or discovery(),
        definition=definition,
    )


class FakeModel:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def propose(self, received_intent, received_discovery):
        self.calls += 1
        if not self.results:
            return proposal(for_intent=received_intent, for_discovery=received_discovery)
        return self.results.pop(0)


def test_separate_budgets_and_exhaustion_block_with_inspection():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    budget = RunBudget(
        max_model_proposals=1,
        max_tool_calls=1,
        max_action_attempts=1,
        max_verification_attempts=1,
        max_repair_trials=1,
    )
    run_id = app.begin_run("inventory-read", budget=budget)
    app.admit_transition(
        run_id,
        behavior="tool_call",
        subject="read",
        input_state={"n": 1},
        budget_dimension="tool_calls",
        run_budget=budget,
    )
    with pytest.raises(BudgetExhaustedError, match="tool_calls") as exc:
        app.admit_transition(
            run_id,
            behavior="tool_call",
            subject="read",
            input_state={"n": 2},
            budget_dimension="tool_calls",
            run_budget=budget,
            state_changed=True,
        )
    assert exc.value.budget == "tool_calls"
    summary = app.inspect_run(run_id)
    assert summary.status == "blocked"
    assert summary.exhausted_budget == "tool_calls"
    assert summary.last_transition
    assert summary.next_required
    assert "tool_calls" in (summary.blocked_reason or "")


def test_repeated_transition_without_state_change_blocks():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    run_id = app.begin_run("inventory-read", budget=RunBudget(max_tool_calls=5))
    payload = {"selector": "role:save"}
    app.admit_transition(
        run_id,
        behavior="selector_candidate",
        subject="save",
        input_state=payload,
        budget_dimension="tool_calls",
    )
    with pytest.raises(RepeatedTransitionError):
        app.admit_transition(
            run_id,
            behavior="selector_candidate",
            subject="save",
            input_state=payload,
            budget_dimension="tool_calls",
        )
    summary = app.inspect_run(run_id)
    assert summary.status == "blocked"
    assert "repeated transition" in (summary.blocked_reason or "")
    assert "deterministic" in (summary.next_required or "")


def test_alternating_fallback_loop_is_fingerprinted_per_state():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    run_id = app.begin_run("inventory-read", budget=RunBudget(max_tool_calls=5))
    app.admit_transition(
        run_id,
        behavior="fallback",
        subject="click",
        input_state={"strategy": "role"},
        budget_dimension="tool_calls",
    )
    app.admit_transition(
        run_id,
        behavior="fallback",
        subject="click",
        input_state={"strategy": "css"},
        budget_dimension="tool_calls",
    )
    with pytest.raises(RepeatedTransitionError):
        app.admit_transition(
            run_id,
            behavior="fallback",
            subject="click",
            input_state={"strategy": "role"},
            budget_dimension="tool_calls",
        )


def test_repeated_proposals_share_fingerprint_until_discovery_changes():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    budget = RunBudget(max_model_proposals=3, max_tool_calls=3)
    run_id = app.begin_run("inventory-read", budget=budget)
    model = FakeModel([])
    first = app.propose(
        intent(),
        discovery(),
        model,
        ProposalBudget(),
        run_id=run_id,
        run_budget=budget,
    )
    assert first.proposal_id
    with pytest.raises(RepeatedTransitionError):
        app.propose(
            intent(),
            discovery(),
            model,
            ProposalBudget(),
            run_id=run_id,
            run_budget=budget,
        )
    assert app.inspect_run(run_id).status == "blocked"

    # Deterministic discovery change admits another proposal on a fresh run.
    run_id_2 = app.begin_run("inventory-read", budget=budget)
    second = app.propose(
        intent(),
        discovery(
            selectors=(SelectorEvidence("role", "inventory total", True),),
            evidence_id="discovery_2",
        ),
        model,
        ProposalBudget(),
        run_id=run_id_2,
        run_budget=budget,
    )
    assert second.proposal_id
    assert model.calls == 2


def test_verification_loop_exhausts_budget():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    budget = RunBudget(
        max_tool_calls=5,
        max_action_attempts=5,
        max_verification_attempts=1,
    )
    run_id = app.begin_run("inventory-read", budget=budget)
    app.admit_transition(
        run_id,
        behavior="verification",
        subject="read",
        input_state={"attempt": 1},
        budget_dimension="verification_attempts",
        run_budget=budget,
    )
    with pytest.raises(BudgetExhaustedError, match="verification_attempts"):
        app.admit_transition(
            run_id,
            behavior="verification",
            subject="read",
            input_state={"attempt": 2},
            budget_dimension="verification_attempts",
            run_budget=budget,
            state_changed=True,
        )


def test_models_cannot_raise_budgets_or_force_success_via_inputs():
    app = AutomationApplication(store=InMemoryEventStore())

    class BadModel:
        def propose(self, received_intent, received_discovery):
            bad = proposal()
            return AutomationProposal(
                proposal_id=bad.proposal_id,
                intent=bad.intent,
                discovery=bad.discovery,
                definition=AutomationDefinition(
                    definition_id="inventory-read",
                    name="Read inventory",
                    success_check="inventory count is present",
                    actions=(
                        AutomationAction(
                            action_id="read-inventory",
                            capability="read",
                            action_class="R0",
                            success_check="inventory count is present",
                            inputs={"max_model_proposals": 999, "force_success": True},
                        ),
                    ),
                ),
            )

    with pytest.raises(AuthorityError, match="cannot increase budgets"):
        app.propose(intent(), discovery(), BadModel())


def test_polling_does_not_swallow_persistent_exceptions():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    run_id = app.begin_run("inventory-read", budget=RunBudget(max_tool_calls=3))

    def boom():
        raise RuntimeError("selector still missing")

    with pytest.raises(RuntimeError, match="selector still missing"):
        app.poll_until(run_id, boom, subject="selector", input_state={"page": "form"})


def test_execute_read_only_records_budget_usage():
    app = AutomationApplication(store=InMemoryEventStore())
    app.register_definition(read_def())
    summary = app.execute_read_only(
        "inventory-read",
        lambda _definition, _run_id: ToolResult(value={"count": 3}),
        lambda result: VerificationResult(passed="count" in result.value, message="ok"),
        budget=RunBudget(),
    )
    assert summary.status == "completed"
    assert summary.budget_usage["tool_calls"] == 1
    assert summary.budget_usage["action_attempts"] == 1
    assert summary.budget_usage["verification_attempts"] == 1
