"""Object and relation schemas for the first-party RPA automation pack."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ActionClass = Literal["R0", "R1", "R2", "R3", "R4"]
RunStatus = Literal["running", "completed", "failed"]
AttemptStatus = Literal["started", "succeeded", "failed"]


class AutomationDefinitionData(BaseModel):
    definition_id: str
    version: str
    content_hash: str
    name: str
    capability: str
    action_class: ActionClass
    target: str
    success_check: str
    expected_value: str | None = None


class AutomationRunData(BaseModel):
    run_id: str
    definition_id: str
    definition_version: str
    status: RunStatus
    failure_kind: str | None = None


class ActionAttemptData(BaseModel):
    attempt_id: str
    run_id: str
    capability: str
    action_class: ActionClass
    status: AttemptStatus
    tool_output: dict[str, Any] = Field(default_factory=dict)


class VerificationResultData(BaseModel):
    verification_id: str
    attempt_id: str
    run_id: str
    passed: bool
    failure_kind: str | None = None
    message: str = ""
    observed_value: str | None = None


class EvidenceReferenceData(BaseModel):
    evidence_id: str
    run_id: str
    attempt_id: str
    kind: str
    path: str
    redacted: bool = True
