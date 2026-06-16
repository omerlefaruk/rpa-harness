from __future__ import annotations

from projects.example_data_verification.workflow import ExampleDataVerificationWorkflow


def test_example_data_verification_project_workflow_has_expected_name():
    assert ExampleDataVerificationWorkflow.name == "example_data_verification"
