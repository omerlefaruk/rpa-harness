"""Versioned operation catalog for MCP/CLI adapters over AutomationApplication.

Adapters contain no lifecycle or authority logic; they invoke these operations only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CATALOG_VERSION = "v1"

# operation -> (input fields, domain error codes)
OPERATION_CATALOG: dict[str, dict[str, Any]] = {
    "workspace_status": {
        "inputs": ("workspace",),
        "outputs": ("product_version", "runtime_version", "status"),
        "errors": ("workspace_missing",),
        "auth": "none",
    },
    "workspace_upgrade": {
        "inputs": ("workspace", "product_version", "release_source"),
        "outputs": ("status",),
        "errors": ("upgrade_failed", "incompatible"),
        "auth": "operator",
    },
    "workspace_rollback": {
        "inputs": ("workspace",),
        "outputs": ("status",),
        "errors": ("rollback_failed",),
        "auth": "operator",
    },
    "validate_proposal": {
        "inputs": ("proposal",),
        "outputs": ("accepted", "errors", "code"),
        "errors": ("automation_proposal_invalid", "automation_proposal_input_invalid"),
        "auth": "none",
    },
    "propose": {
        "inputs": ("workspace", "proposal"),
        "outputs": ("proposal",),
        "errors": ("automation_authority_denied", "automation_repeated_transition"),
        "auth": "writer",
    },
    "register_proposal": {
        "inputs": ("workspace", "proposal"),
        "outputs": ("definition_version",),
        "errors": ("automation_proposal_invalid",),
        "auth": "writer",
    },
    "grant_approval": {
        "inputs": (
            "workspace",
            "definition_id",
            "version",
            "actor",
            "target_scope",
            "record_scope",
            "side_effect_scope",
            "expires_at",
        ),
        "outputs": ("approval_grant",),
        "errors": ("automation_approval_denied", "automation_authority_denied"),
        "auth": "approver",
    },
    "inspect_run": {
        "inputs": ("workspace", "run_id"),
        "outputs": ("run_summary",),
        "errors": ("unknown_run",),
        "auth": "reader",
    },
    "execute_read_only": {
        "inputs": ("workspace", "definition_id", "op", "port"),
        "outputs": ("run_summary",),
        "errors": ("unknown_definition", "automation_authority_denied"),
        "auth": "writer",
    },
    "execute_write": {
        "inputs": (
            "workspace",
            "definition_id",
            "version",
            "grant_id",
            "actor",
            "op",
            "port",
        ),
        "outputs": ("run_summary",),
        "errors": (
            "automation_approval_denied",
            "automation_duplicate_write",
            "automation_authority_denied",
        ),
        "auth": "writer",
    },
    "reconcile": {
        "inputs": ("workspace", "run_id", "conclusion"),
        "outputs": ("run_summary",),
        "errors": ("automation_reconciliation_invalid",),
        "auth": "writer",
    },
    "propose_repair": {
        "inputs": ("workspace", "repair_request"),
        "outputs": ("repair_proposal",),
        "errors": ("automation_repair_rejected",),
        "auth": "writer",
    },
    "trial_repair": {
        "inputs": ("workspace", "repair_id", "op"),
        "outputs": ("trial",),
        "errors": ("automation_repair_rejected", "automation_budget_exhausted"),
        "auth": "writer",
    },
    "promote_repair": {
        "inputs": ("workspace", "repair_id", "trial_id"),
        "outputs": ("definition_version",),
        "errors": ("automation_repair_rejected",),
        "auth": "approver",
    },
    "export_evidence": {
        "inputs": ("workspace", "run_id"),
        "outputs": ("evidence_references",),
        "errors": ("unknown_run",),
        "auth": "reader",
    },
}


@dataclass(frozen=True)
class OperationContract:
    name: str
    version: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    errors: tuple[str, ...]
    authorization: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def list_operations() -> tuple[OperationContract, ...]:
    return tuple(
        OperationContract(
            name=name,
            version=CATALOG_VERSION,
            inputs=tuple(spec["inputs"]),
            outputs=tuple(spec["outputs"]),
            errors=tuple(spec["errors"]),
            authorization=str(spec["auth"]),
        )
        for name, spec in sorted(OPERATION_CATALOG.items())
    )


def operation_contract(name: str) -> OperationContract:
    if name not in OPERATION_CATALOG:
        raise KeyError(f"Unknown operation: {name}")
    return next(item for item in list_operations() if item.name == name)


# MCP must never expose these.
FORBIDDEN_MCP_TOOLS = frozenset(
    {
        "shell",
        "exec",
        "run_python",
        "raw_driver",
        "playwright_click",
        "desktop_click_raw",
        "arbitrary_path_write",
    }
)
