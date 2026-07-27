"""ActiveGraph-native automation application seam."""

from harness.automation.application import (
    AutomationApplication,
    AutomationDefinition,
    EvidenceReference,
    RunSummary,
    ToolResult,
    VerificationResult,
    WorkspaceRuntimeActiveError,
)
from harness.automation.authoring import (
    AutomationAction,
    AutomationIntent,
    AutomationProposal,
    DefinitionVersion,
    DiscoveryAdapter,
    DiscoveryEvidence,
    ProposalBudget,
    ProposalModelAdapter,
    ProposalValidation,
    ProposalValidationError,
    SelectorEvidence,
    proposal_from_dict,
)
from harness.automation.pack import pack
from harness.automation.workspace_runtime import (
    RuntimeManifest,
    WorkspaceRuntimeError,
    WorkspaceRuntimeIncompatibleError,
    WorkspaceRuntimeManager,
    WorkspaceStatus,
    default_manifest,
)

__all__ = [
    "AutomationApplication",
    "AutomationAction",
    "AutomationDefinition",
    "AutomationIntent",
    "AutomationProposal",
    "DefinitionVersion",
    "DiscoveryAdapter",
    "DiscoveryEvidence",
    "EvidenceReference",
    "RunSummary",
    "ProposalBudget",
    "ProposalModelAdapter",
    "ProposalValidation",
    "ProposalValidationError",
    "SelectorEvidence",
    "ToolResult",
    "VerificationResult",
    "WorkspaceRuntimeActiveError",
    "pack",
    "proposal_from_dict",
    "RuntimeManifest",
    "WorkspaceRuntimeError",
    "WorkspaceRuntimeIncompatibleError",
    "WorkspaceRuntimeManager",
    "WorkspaceStatus",
    "default_manifest",
]
