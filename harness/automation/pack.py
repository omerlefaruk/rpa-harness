"""First-party ActiveGraph pack declarations for the RPA lifecycle surface.

Tools and behaviors in this module are pack **declarations** only. They describe
object types, relations, and tool schemas for ActiveGraph; they do not execute
RPA actions. The product host ``AutomationApplication`` is the only execution
path: adapters injected by the host perform real work under lifecycle authority.
"""

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
    description="Declared R0 read-only action schema (execution is host-owned).",
    input_schema=ReadOnlyActionInput,
    output_schema=ReadOnlyActionOutput,
    deterministic=False,
)
def read_only_action(args, ctx):
    """Pack tool declaration only — not an executable runtime.

    AutomationApplication adapters invoke real capability ports; this function
    must never be called as a standalone driver.
    """

    raise RuntimeError("read_only_action must be invoked by an AutomationApplication adapter")


@tool(
    name="approval_gated_write",
    description="Declared approval-gated write schema (execution is host-owned).",
    input_schema=WriteActionInput,
    output_schema=WriteActionOutput,
    deterministic=False,
)
def approval_gated_write(args, ctx):
    """Pack tool declaration only — not an executable runtime.

    Writes run only through AutomationApplication.execute_write with grants.
    """

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
