"""JSON-request adapters for MCP/CLI over AutomationApplication.

The agent (external LLM) drafts JSON. These ops only call the application seam
and capability ports — no lifecycle logic in the transport layer.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from harness.automation.application import (
    AuthorityError,
    AutomationApplication,
    AutomationDefinition,
    MappingSecretAdapter,
    ReconciliationResult,
    ToolResult,
    VerificationResult,
)
from harness.automation.authoring import (
    AutomationAction,
    AutomationIntent,
    AutomationProposal,
    DiscoveryEvidence,
    SelectorEvidence,
    proposal_from_dict,
)
from harness.automation.capabilities import (
    CapabilityExecutor,
    CapabilityOp,
    FakeApi,
    FakeBrowser,
    FakeDesktop,
    FakeExcel,
)


def proposal_dict_to_contract(data: dict[str, Any]) -> AutomationProposal:
    return proposal_from_dict(data, AutomationDefinition)


def selector_from_dict(value: dict[str, Any] | None) -> SelectorEvidence | None:
    if not value:
        return None
    return SelectorEvidence(
        strategy=str(value["strategy"]),
        locator=str(value["locator"]),
        verified=bool(value.get("verified", False)),
    )


def capability_op_from_dict(data: dict[str, Any]) -> CapabilityOp:
    return CapabilityOp(
        name=str(data["name"]),
        action_class=str(data.get("action_class", "R0")),
        read_only=bool(data.get("read_only", True)),
        inputs=dict(data.get("inputs") or {}),
        selector=selector_from_dict(data.get("selector")),
        success_check=str(data.get("success_check", "")),
    )


def build_executor(port: str = "fake_browser") -> CapabilityExecutor:
    """Build a CapabilityExecutor for the named port.

    Fake ports (default for agent loops / CI):
      fake_browser, fake_api, fake_excel, fake_desktop

    Real ports (production hosts; optional driver deps):
      browser → SyncPlaywrightBrowserPort
      api → HttpApiPort
      excel → ExcelFilePort
      desktop → DesktopUiaPort

    MCP/CLI never expose raw drivers; they only select these named ports.
    """

    if port == "fake_browser":
        return CapabilityExecutor(browser=FakeBrowser())
    if port == "fake_api":
        return CapabilityExecutor(api=FakeApi())
    if port == "fake_excel":
        return CapabilityExecutor(excel=FakeExcel())
    if port == "fake_desktop":
        return CapabilityExecutor(desktop=FakeDesktop())
    if port == "browser":
        from harness.automation.ports import SyncPlaywrightBrowserPort

        return CapabilityExecutor(browser=SyncPlaywrightBrowserPort())
    if port == "api":
        from harness.automation.ports import HttpApiPort

        return CapabilityExecutor(api=HttpApiPort())
    if port == "excel":
        from harness.automation.ports import ExcelFilePort

        return CapabilityExecutor(excel=ExcelFilePort())
    if port == "desktop":
        from harness.automation.ports import DesktopUiaPort

        return CapabilityExecutor(desktop=DesktopUiaPort())
    raise ValueError(f"unsupported capability port: {port}")


def default_verify(result: ToolResult) -> VerificationResult:
    if result.write_outcome == "unknown":
        return VerificationResult(
            passed=False,
            message="write outcome unknown",
            failure_kind="needs_reconciliation",
        )
    # Prefer explicit success markers from capability fakes/ports.
    if result.value.get("filled") is True or result.value.get("clicked") is True:
        return VerificationResult(passed=True, message="write applied")
    if result.value.get("written"):
        return VerificationResult(passed=True, message="rows written")
    if result.value.get("typed") is True:
        return VerificationResult(passed=True, message="typed")
    if result.value.get("status") in {200, 201}:
        return VerificationResult(passed=True, message="http ok")
    if "count" in str(result.value) or "text" in result.value or "rows" in result.value:
        return VerificationResult(passed=True, message="value present")
    if result.value:
        return VerificationResult(passed=True, message="non-empty result")
    return VerificationResult(
        passed=False,
        message="empty or unsuccessful result",
        failure_kind="verification_failed",
    )


def execute_read_only_request(
    app: AutomationApplication, request: dict[str, Any]
) -> dict[str, Any]:
    definition_id = str(request["definition_id"])
    op = capability_op_from_dict(request["op"])
    if not op.read_only or op.action_class != "R0":
        raise AuthorityError("read-only transport accepts only bound R0 operations")
    executor = build_executor(str(request.get("port", "fake_browser")))
    if request.get("fixture_result") is not None:
        fixture = ToolResult(**request["fixture_result"])

        def adapter(_definition, _run_id):
            return fixture

        summary = app.execute_read_only(
            definition_id, adapter, default_verify, operation_id=op.name
        )
    else:
        summary = app.execute_read_only(
            definition_id,
            executor.as_read_adapter(op),
            default_verify,
            operation_id=op.name,
        )
    return summary.to_dict()


def execute_write_request(app: AutomationApplication, request: dict[str, Any]) -> dict[str, Any]:
    definition_id = str(request["definition_id"])
    version = int(request["version"])
    grant_id = str(request["grant_id"])
    actor = str(request["actor"])
    op = capability_op_from_dict(request["op"])
    if op.read_only or op.action_class == "R0":
        raise AuthorityError("write transport accepts only write-capable operations")
    executor = build_executor(str(request.get("port", "fake_browser")))
    secrets = dict(request.get("secrets") or {})
    secret_adapter = MappingSecretAdapter(secrets) if secrets else None

    if request.get("fixture_result") is not None:
        fixture = ToolResult(**request["fixture_result"])

        def adapter(_definition, _run_id, *, secrets, action):
            del secrets, action
            return fixture

        summary = app.execute_write(
            definition_id,
            version=version,
            grant_id=grant_id,
            adapter=adapter,
            verify=default_verify,
            actor=actor,
            secret_adapter=secret_adapter,
            principal="agent",
        )
    else:
        summary = app.execute_write(
            definition_id,
            version=version,
            grant_id=grant_id,
            adapter=executor.as_write_adapter(op),
            verify=default_verify,
            actor=actor,
            secret_adapter=secret_adapter,
            principal="agent",
        )
    return summary.to_dict()


def reconcile_request(app: AutomationApplication, request: dict[str, Any]) -> dict[str, Any]:
    run_id = str(request["run_id"])
    conclusion = str(request["conclusion"])
    evidence = dict(request.get("evidence") or {})
    observed_value = dict(request.get("observed_value") or {})
    message = str(request.get("message") or conclusion)

    def read_probe() -> ToolResult:
        return ToolResult(value=observed_value, evidence=evidence)

    def conclude(_observed: ToolResult) -> ReconciliationResult:
        return ReconciliationResult(conclusion=conclusion, evidence=evidence, message=message)

    summary = app.reconcile(
        run_id,
        read_probe=read_probe,
        conclude=conclude,
        verify=default_verify if conclusion == "applied" else None,
    )
    return summary.to_dict()


def propose_repair_request(app: AutomationApplication, request: dict[str, Any]) -> dict[str, Any]:
    discovery_value = request["discovery"]
    definition_value = dict(request["proposed_definition"])
    actions = tuple(
        AutomationAction(
            action_id=str(item["action_id"]),
            capability=str(item["capability"]),
            action_class=str(item["action_class"]),
            success_check=str(item["success_check"]),
            selector=selector_from_dict(item.get("selector")),
            credential_names=tuple(item.get("credential_names") or ()),
            inputs=dict(item.get("inputs") or {}),
        )
        for item in definition_value.get("actions") or ()
    )
    definition = AutomationDefinition(
        definition_id=str(definition_value["definition_id"]),
        name=str(definition_value["name"]),
        success_check=str(definition_value["success_check"]),
        action_id=str(definition_value.get("action_id", "read")),
        action_class=str(definition_value.get("action_class", "R0")),
        read_only=bool(definition_value.get("read_only", True)),
        actions=actions,
        target_scope=str(definition_value.get("target_scope", "")),
        record_scope=str(definition_value.get("record_scope", "")),
        side_effect_scope=str(definition_value.get("side_effect_scope", "")),
        idempotency_scope=str(definition_value.get("idempotency_scope", "")),
        credential_names=tuple(definition_value.get("credential_names") or ()),
    )

    repair = app.propose_repair(
        parent_definition_id=str(request["parent_definition_id"]),
        parent_version=int(request["parent_version"]),
        failure_run_id=str(request["failure_run_id"]),
        failure_kind=str(request.get("failure_kind", "selector_failed")),
        discovery=DiscoveryEvidence(
            evidence_id=str(discovery_value["evidence_id"]),
            selectors=tuple(
                SelectorEvidence(**item) for item in discovery_value.get("selectors", ())
            ),
            observed_capabilities=tuple(discovery_value.get("observed_capabilities") or ()),
        ),
        proposed_definition=definition,
        rationale=str(request.get("rationale", "")),
        surface=str(request.get("surface", "browser")),
    )
    return repair.to_dict()


def trial_repair_request(app: AutomationApplication, request: dict[str, Any]) -> dict[str, Any]:
    repair_id = str(request["repair_id"])
    if request.get("fixture_result") is not None:
        fixture = ToolResult(**request["fixture_result"])

        def adapter(_d, _r):
            return fixture

        trial = app.trial_repair(repair_id, adapter=adapter, verify=default_verify)
    else:
        op = capability_op_from_dict(request["op"])
        executor = build_executor(str(request.get("port", "fake_browser")))
        trial = app.trial_repair(
            repair_id, adapter=executor.as_read_adapter(op), verify=default_verify
        )
    return trial.to_dict()


def promote_repair_request(app: AutomationApplication, request: dict[str, Any]) -> dict[str, Any]:
    version = app.promote_repair(str(request["repair_id"]), trial_id=str(request["trial_id"]))
    return version.to_dict()


def intent_from_dict(data: dict[str, Any]) -> AutomationIntent:
    return AutomationIntent(
        intent_id=str(data["intent_id"]),
        name=str(data["name"]),
        objective=str(data["objective"]),
        required_capabilities=tuple(data.get("required_capabilities") or ()),
        unresolved_business_ambiguities=tuple(data.get("unresolved_business_ambiguities") or ()),
        schema_version=str(data.get("schema_version", "v1")),
    )


def discovery_from_dict(data: dict[str, Any]) -> DiscoveryEvidence:
    return DiscoveryEvidence(
        evidence_id=str(data["evidence_id"]),
        selectors=tuple(SelectorEvidence(**item) for item in data.get("selectors") or ()),
        observed_capabilities=tuple(data.get("observed_capabilities") or ()),
        schema_version=str(data.get("schema_version", "v1")),
    )


def propose_from_request(app: AutomationApplication, request: dict[str, Any]) -> dict[str, Any]:
    """Admit a model-authored proposal under budgets without invoking external LLMs.

    The AI agent is the model: it supplies the full proposal JSON. Harness only
    validates authority escape and optional transition fingerprinting.
    """

    proposal = proposal_dict_to_contract(request["proposal"])
    intent = proposal.intent
    discovery = proposal.discovery

    class EchoModel:
        def propose(self, received_intent, received_discovery):
            del received_intent, received_discovery
            return proposal

    result = app.propose(intent, discovery, EchoModel())
    return {
        "proposal_id": result.proposal_id,
        "definition_id": result.definition.definition_id,
        "schema_version": result.schema_version,
        "proposal": asdict(result),
    }


def load_json(path: str | Path) -> dict[str, Any]:
    return dict(__import__("json").loads(Path(path).read_text(encoding="utf-8")))
