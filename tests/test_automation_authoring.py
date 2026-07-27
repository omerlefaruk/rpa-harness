from dataclasses import asdict

import pytest
from activegraph.store import InMemoryEventStore

from harness.automation import (
    AutomationAction,
    AutomationApplication,
    AutomationDefinition,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    ProposalBudget,
    ProposalValidationError,
    SelectorEvidence,
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


def discovery(**changes):
    values = {
        "evidence_id": "discovery_1",
        "selectors": (SelectorEvidence("role", "inventory count", True),),
        "observed_capabilities": ("read",),
    }
    values.update(changes)
    return DiscoveryEvidence(**values)


def proposal(**changes):
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
    )
    values = {
        "proposal_id": "proposal_1",
        "intent": intent(),
        "discovery": discovery(),
        "definition": definition,
    }
    values.update(changes)
    return AutomationProposal(**values)


class FakeDiscovery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def discover(self, received_intent):
        self.calls.append(received_intent)
        return self.result


class FakeModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def propose(self, received_intent, received_discovery):
        self.calls.append((received_intent, received_discovery))
        return self.result


def test_application_authors_with_fake_adapters_and_registers_immutable_versions():
    app = AutomationApplication(store=InMemoryEventStore())
    candidate = proposal()
    discovery_adapter = FakeDiscovery(candidate.discovery)
    model = FakeModel(candidate)

    authored = app.discover_and_propose(intent(), discovery_adapter, model)
    first = app.register_proposal(authored)
    second = app.register_proposal(authored)

    assert discovery_adapter.calls == [intent()]
    assert model.calls == [(intent(), candidate.discovery)]
    assert first.version == 1
    assert second.version == 2
    assert first.content_hash == second.content_hash
    assert app.definition_versions("inventory-read") == (first, second)
    assert "[REDACTED]" not in str(asdict(first))


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (
            proposal(intent=intent(unresolved_business_ambiguities=("which warehouse?",))),
            "ambiguity",
        ),
        (proposal(intent=intent(required_capabilities=("shell",))), "unknown capabilities"),
        (
            proposal(
                definition=AutomationDefinition(
                    definition_id="bad",
                    name="Bad",
                    success_check="present",
                    actions=(
                        AutomationAction("bad", "read", "W1", "present"),
                    ),
                )
            ),
            "invalid action class",
        ),
        (
            proposal(
                definition=AutomationDefinition(
                    definition_id="bad-write-class",
                    name="Bad write",
                    success_check="present",
                    read_only=False,
                    action_class="R0",
                    action_id="write",
                    actions=(
                        AutomationAction("write", "write", "R0", "present"),
                    ),
                )
            ),
            "invalid action class",
        ),
        (
            proposal(
                definition=AutomationDefinition(
                    definition_id="bad",
                    name="Bad",
                    success_check="present",
                    actions=(
                        AutomationAction(
                            "bad",
                            "read",
                            "R0",
                            "present",
                            selector=SelectorEvidence("xpath", "//button", False),
                        ),
                    ),
                )
            ),
            "weak selector",
        ),
        (
            proposal(
                definition=AutomationDefinition(
                    definition_id="bad",
                    name="Bad",
                    success_check="present",
                    actions=(
                        AutomationAction(
                            "bad", "read", "R0", "present", inputs={"password": "not-a-secret-ref"}
                        ),
                    ),
                )
            ),
            "plaintext secrets",
        ),
    ],
)
def test_registration_rejects_unsafe_or_ambiguous_proposals(candidate, message):
    app = AutomationApplication(store=InMemoryEventStore())

    with pytest.raises(ProposalValidationError, match=message):
        app.register_proposal(candidate)


def test_proposal_budget_and_model_output_type_are_enforced():
    app = AutomationApplication(store=InMemoryEventStore())

    with pytest.raises(ValueError, match="budgets"):
        app.propose(intent(), discovery(), FakeModel(proposal()), ProposalBudget(max_model_calls=0))
    with pytest.raises(TypeError, match="AutomationProposal"):
        app.propose(intent(), discovery(), FakeModel({}))


def test_cli_validate_and_register_share_application_error_codes(tmp_path):
    import json
    import subprocess
    import sys
    from dataclasses import asdict

    good = proposal()
    bad = proposal(intent=intent(unresolved_business_ambiguities=("which warehouse?",)))
    good_path = tmp_path / "good.json"
    bad_path = tmp_path / "bad.json"
    good_path.write_text(json.dumps(asdict(good), default=str), encoding="utf-8")
    bad_path.write_text(json.dumps(asdict(bad), default=str), encoding="utf-8")
    workspace = tmp_path / "ws"

    def run_cli(*args: str):
        return subprocess.run(
            [sys.executable, "-m", "harness.cli", *args],
            text=True,
            capture_output=True,
            check=False,
        )

    accepted = run_cli("--automation-validate-proposal", str(good_path))
    rejected = run_cli("--automation-validate-proposal", str(bad_path))
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["accepted"] is True
    assert rejected.returncode == 2
    assert json.loads(rejected.stdout)["code"] == "automation_proposal_invalid"

    registered = run_cli(
        "--automation-register-proposal",
        str(good_path),
        "--automation-workspace",
        str(workspace),
    )
    assert registered.returncode == 0, registered.stderr
    version = json.loads(registered.stdout)
    assert version["version"] == 1
    assert version["content_hash"]

    failed_register = run_cli(
        "--automation-register-proposal",
        str(bad_path),
        "--automation-workspace",
        str(workspace),
    )
    assert failed_register.returncode == 2
    assert json.loads(failed_register.stderr)["code"] == "automation_proposal_invalid"
