---
name: rpa_harness_automation_builder
description: Build, inspect, repair, or improve deterministic RPA workflows in rpa-harness.
---

# rpa-harness Automation Builder Skill

Use this when creating, repairing, inspecting, or improving an RPA automation with rpa-harness.

Core rule: do not guess automation behavior. Build deterministic workflows from inspection evidence, explicit success checks, and operator-approved risky actions.

Standard flow:

1. Search RPA Memory first. If unavailable, say so and continue from repo evidence.
2. Identify target type: browser, desktop, API, Excel/data, or mixed.
3. Identify inputs, outputs, secret names, risky actions, and success criteria.
4. Validate or preflight existing workflows.
5. Inspect targets before writing selectors.
6. Draft phases and steps.
7. Add success checks to every step.
8. Mark side effects, retryability, and approvals.
9. Dry-run safe phases or one record.
10. Inspect report, timeline, records, evidence bundle, and repair packet.

Browser selector priority:

1. data-testid
2. role/name
3. label
4. placeholder
5. text
6. stable id
7. CSS
8. XPath

Desktop selector priority:

1. automation_id
2. name/control_type
3. class/control_type
4. tree path
5. image anchor
6. coordinate fallback

Every generated step needs:

- `id`
- `phase`
- `action`
- selector or target when applicable
- `success_check`
- `side_effect` when applicable
- `retryable`
- `requires_approval` for risky actions
- `selector_quality` when weak

Risky actions require approval or a human gate: submit, official upload, delete, external send, payment, irreversible update, MFA/CAPTCHA, and weak legacy desktop external writes.

Useful commands:

```bash
python main.py --validate-yaml workflow.yaml
python main.py --preflight-yaml workflow.yaml
python main.py --run-yaml workflow.yaml --phase login
python main.py --run-yaml workflow.yaml --pause-before submit
python main.py --runs-list
python main.py --runs-show RUN_ID
python main.py --logs-show RUN_ID
python main.py --report-open RUN_ID
python main.py --build-start task.md
python main.py --capture-desktop "Legacy ERP" --capture-session-dir builder_sessions/SESSION
python main.py --discovery-validate-fixtures
python main.py --repair-selector RUN_ID
python main.py --retry-run RUN_ID --failed-records
```

Do not claim production-ready unless dry-run or one-record evidence supports it.
