"""First-party ActiveGraph pack for rpa-harness automation lifecycle."""

from __future__ import annotations

from activegraph.packs import EmptySettings, ObjectType, Pack

from harness.activegraph_app.pack.types import (
    ActionAttemptData,
    AutomationDefinitionData,
    AutomationRunData,
    EvidenceReferenceData,
    VerificationResultData,
)
from harness.activegraph_app.workspace import PACK_NAME, PACK_VERSION

OBJECT_TYPES = (
    ObjectType(
        name="automation_definition",
        schema=AutomationDefinitionData,
        description="Immutable automation definition version.",
    ),
    ObjectType(
        name="automation_run",
        schema=AutomationRunData,
        description="One execution of a definition version.",
    ),
    ObjectType(
        name="action_attempt",
        schema=ActionAttemptData,
        description="One governed action attempt within a run.",
    ),
    ObjectType(
        name="verification_result",
        schema=VerificationResultData,
        description="Explicit post-action verification outcome.",
    ),
    ObjectType(
        name="evidence_reference",
        schema=EvidenceReferenceData,
        description="Pointer to redacted evidence outside the event log.",
    ),
)


def build_pack(*, tools: tuple = ()) -> Pack:
    return Pack(
        name=PACK_NAME,
        version=PACK_VERSION,
        description="First-party RPA automation lifecycle pack for ActiveGraph.",
        object_types=OBJECT_TYPES,
        tools=tools,
        settings_schema=EmptySettings,
    )


# Default pack export for entry-point discovery (no tools until host injects).
pack = build_pack()
