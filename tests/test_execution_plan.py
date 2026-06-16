from harness.rpa.execution_plan import build_execution_plan
from harness.rpa.schema import normalize_default_schema_to_runner


def test_execution_plan_expands_for_each_records_and_filters_only_record():
    workflow = {
        "id": "looped",
        "name": "Looped",
        "version": "1.0",
        "type": "api",
        "steps": [
            {
                "id": "process_row",
                "phase": "process_records",
                "for_each": {"input": "rows", "record_id": "invoice_id"},
                "action": {"type": "no_op"},
                "success_check": [{"type": "always_pass"}],
            }
        ],
    }

    plan = build_execution_plan(
        workflow,
        inputs={"rows": [{"invoice_id": "A-1"}, {"invoice_id": "B-2"}]},
        only_record="B-2",
    )

    assert [unit.step["record_id"] for unit in plan.units] == ["B-2"]
    assert plan.units[0].record == {"invoice_id": "B-2"}
    assert plan.summary() == {
        "total_units": 1,
        "total_phases": 1,
        "record_units": 1,
        "phases": ["process_records"],
    }


def test_default_schema_phase_for_each_is_preserved_for_execution_plan():
    workflow = {
        "schema_version": 2,
        "name": "Default Schema Loop",
        "metadata": {"reliability_level": "api"},
        "inputs": {
            "primary": {
                "variables": {
                    "rows": [{"invoice_id": "A-1"}, {"invoice_id": "B-2"}],
                }
            }
        },
        "targets": {"api": {"type": "api"}},
        "phases": [
            {
                "id": "process_records",
                "for_each": {"input": "rows", "record_id": "invoice_id"},
                "steps": [
                    {
                        "id": "process_row",
                        "action": {"type": "no_op"},
                        "success_checks": [{"type": "always_pass"}],
                    }
                ],
            }
        ],
    }

    runner_workflow = normalize_default_schema_to_runner(workflow)
    plan = build_execution_plan(runner_workflow, inputs=runner_workflow["inputs"])

    assert [unit.step["record_id"] for unit in plan.units] == ["A-1", "B-2"]
