"""
Verifier — validates and runs verification contracts for workflow steps.
"""

from typing import Any, Dict, List

from harness.verification.contract import (
    SuccessCheck,
    VerificationResult,
    validate_workflow,
    validate_workflow_step,
)
from harness.verification.checks import run_all_checks


class WorkflowVerifier:
    def __init__(self):
        pass

    def validate(self, workflow: dict) -> List[str]:
        return validate_workflow(workflow)

    def validate_step(self, step: dict) -> List[str]:
        return validate_workflow_step(step)

    def verify_step(self, step: dict, context: Dict[str, Any]) -> List[VerificationResult]:
        checks_data = step.get("success_check", [])
        checks = [SuccessCheck.from_dict(c) for c in checks_data]
        return run_all_checks(checks, context)

    def verify_all(self, workflow: dict, step_contexts: Dict[str, Dict[str, Any]]) -> Dict[str, List[VerificationResult]]:
        results = {}
        for step in workflow.get("steps", []):
            step_id = step.get("id", "unknown")
            ctx = step_contexts.get(step_id, {})
            results[step_id] = self.verify_step(step, ctx)
        return results
