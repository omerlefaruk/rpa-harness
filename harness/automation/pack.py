"""Executable first-party ActiveGraph lifecycle pack.

The pack owns schemas and deterministic materialization. External I/O remains a
host adapter, but lifecycle objects and relations are real graph state.
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


class WorkspaceObject(BaseModel):
    workspace_id: str
    status: str = "active"
    schema_version: str = "1"


class AutomationObject(BaseModel):
    definition_id: str
    name: str
    action_class: str = "R0"
    read_only: bool = True
    status: str = "registered"


class AutomationRevisionObject(BaseModel):
    definition_id: str
    version: int
    content_hash: str
    immutable: bool = True
    source_hash: str = ""
    action_manifest: dict[str, object] = Field(default_factory=dict)


class WorkflowRunObject(BaseModel):
    run_id: str
    definition_id: str
    status: str
    parent_run_id: str = ""
    fork_point: str = ""


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
    content_hash: str = ""
    size: int = 0


class ReadOnlyActionInput(BaseModel):
    run_id: str
    action_id: str


class ReadOnlyActionOutput(BaseModel):
    value: dict[str, object] = Field(default_factory=dict)


@behavior(name="start_read_only_run", on=["rpa.run.started"])
def start_read_only_run(event, graph, ctx):
    """Materialize a run object when a lifecycle start event is accepted."""

    payload = event.payload
    if not payload.get("run_id") or graph.objects(type="workflow_run", where={"run_id": payload["run_id"]}):
        return
    graph.add_object(
        "workflow_run",
        {
            "run_id": payload["run_id"],
            "definition_id": payload.get("definition_id", ""),
            "status": "running",
            "parent_run_id": graph.run_id,
            "fork_point": event.id,
        },
        actor="activegraph",
        caused_by=event.id,
    )


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
        ObjectType("workspace", WorkspaceObject),
        ObjectType("automation", AutomationObject),
        ObjectType("automation_revision", AutomationRevisionObject),
        ObjectType("workflow_run", WorkflowRunObject),
        ObjectType("automation_definition", AutomationDefinitionObject),
        ObjectType("run", RunObject),
        ObjectType("action_attempt", ActionAttemptObject),
        ObjectType("approval_grant", ApprovalGrantObject),
        ObjectType("verification_result", VerificationResultObject),
        ObjectType("evidence_reference", EvidenceReferenceObject),
    ),
    relation_types=(
        RelationType("has_revision", ("automation",), ("automation_revision",)),
        RelationType("defines", ("automation_definition",), ("run",)),
        RelationType("attempts", ("run",), ("action_attempt",)),
        RelationType("authorizes", ("approval_grant",), ("action_attempt",)),
        RelationType("verifies", ("action_attempt",), ("verification_result",)),
        RelationType("evidences", ("run", "workflow_run"), ("evidence_reference",)),
    ),
    behaviors=(start_read_only_run,),
    tools=(read_only_action, approval_gated_write),
    policies=(PackPolicy(name="approval_gated_writes"),),
    settings_schema=RpaPackSettings,
)
