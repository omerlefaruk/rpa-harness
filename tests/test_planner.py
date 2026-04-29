"""Tests for AI planner safety hardening."""

from harness.ai.planner import Plan, PlanStep, TaskPlanner


def test_harden_plan_adds_expected_results_and_done_step():
    plan = Plan(
        task="Submit form",
        steps=[
            PlanStep(
                id=1,
                action="click",
                description="Click submit",
                tool_name="browser_click",
                tool_args={"selector": "#submit"},
                expected_result="",
            )
        ],
    )

    hardened = TaskPlanner()._harden_plan(plan)

    assert [step.action for step in hardened.steps] == ["click", "done"]
    assert hardened.steps[0].expected_result == "Click submit completed"
    assert hardened.steps[1].depends_on == [1]
    assert hardened.metadata["safety_issues"] == []
    assert hardened.metadata["safety_score"] == 1.0


def test_plan_safety_flags_coordinate_first_tool_args():
    plan = Plan(
        task="Click by coordinates",
        steps=[
            PlanStep(
                id=1,
                action="click",
                description="Click button",
                tool_name="browser_click",
                tool_args={"x": 10, "y": 20},
                expected_result="Button clicked",
            ),
            PlanStep(id=2, action="done", description="Done", expected_result="Task finished"),
        ],
    )

    assert plan.safety_issues() == ["step 1 uses coordinate-first tool args"]
    assert plan.safety_score < 1.0
