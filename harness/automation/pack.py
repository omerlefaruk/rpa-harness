"""First-party ActiveGraph pack for the initial verified read-only slice."""

from __future__ import annotations

from activegraph.packs import ObjectType, Pack, PackPolicy, RelationType, behavior, tool
from pydantic import BaseModel, Field


class AutomationDefinitionObject(BaseModel):
    definition_id: str
    name: str
    action_class: str = "R0"
    read_only: bool = True
    success_check: str


class RunObject(BaseModel):
    run_id: str
    definition_id: str
    status: str


class ActionAttemptObject(BaseModel):
    run_id: str
    action_id: str
    read_only: bool = True
    action_class: str = "R0"
    idempotency_scope: str = ""


class ApprovalGrantObject(BaseModel):
    grant_id: str
    definition_id: str
    definition_version: int
    content_hash: str
    actor: str


class VerificationResultObject(BaseModel):
    run_id: str
    passed: bool
    failure_kind: str | None = None


class EvidenceReferenceObject(BaseModel):
    evidence_id: str
    run_id: str
    uri: str


class ReadOnlyActionInput(BaseModel):
    run_id: str
    action_id: str


class ReadOnlyActionOutput(BaseModel):
    value: dict[str, object] = Field(default_factory=dict)


@behavior(name="start_read_only_run", on=["rpa.run.started"])
def start_read_only_run(event, graph, ctx):
    """The product host owns adapter invocation; this behavior declares the lifecycle trigger."""


class WriteActionInput(BaseModel):
    run_id: str
    action_id: str
    grant_id: str
    idempotency_scope: str


class WriteActionOutput(BaseModel):
    value: dict[str, object] = Field(default_factory=dict)
    applied: bool = True


@tool(
    name="read_only_action",
    description="Run a declared R0 read-only action through the product adapter.",
    input_schema=ReadOnlyActionInput,
    output_schema=ReadOnlyActionOutput,
    deterministic=False,
)
def read_only_action(args, ctx):
    """Pack declaration only; adapters are injected by the application host."""

    raise RuntimeError("read_only_action must be invoked by an AutomationApplication adapter")


@tool(
    name="approval_gated_write",
    description="Run a declared approval-gated write through the product adapter.",
    input_schema=WriteActionInput,
    output_schema=WriteActionOutput,
    deterministic=False,
)
def approval_gated_write(args, ctx):
    """Pack declaration only; adapters are injected by the application host."""

    raise RuntimeError("approval_gated_write must be invoked by an AutomationApplication adapter")


class RpaPackSettings(BaseModel):
    evidence_directory: str = "evidence"


pack = Pack(
    name="rpa_automation",
    version="0.1.0",
    description="Typed RPA lifecycle objects and a governed read-only action surface.",
    object_types=(
        ObjectType("automation_definition", AutomationDefinitionObject),
        ObjectType("run", RunObject),
        ObjectType("action_attempt", ActionAttemptObject),
        ObjectType("approval_grant", ApprovalGrantObject),
        ObjectType("verification_result", VerificationResultObject),
        ObjectType("evidence_reference", EvidenceReferenceObject),
    ),
    relation_types=(
        RelationType("defines", ("automation_definition",), ("run",)),
        RelationType("attempts", ("run",), ("action_attempt",)),
        RelationType("authorizes", ("approval_grant",), ("action_attempt",)),
        RelationType("verifies", ("action_attempt",), ("verification_result",)),
        RelationType("evidences", ("run",), ("evidence_reference",)),
    ),
    behaviors=(start_read_only_run,),
    tools=(read_only_action, approval_gated_write),
    policies=(PackPolicy(name="approval_gated_writes"),),
    settings_schema=RpaPackSettings,
)
