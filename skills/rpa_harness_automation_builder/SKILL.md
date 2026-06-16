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
python main.py --copilot-auto task.md --builder-session-id SESSION
python main.py --copilot-answer SESSION --copilot-question-id QUESTION --copilot-response ANSWER
python main.py --copilot-try-url https://example.test --copilot-try-workflow workflow.yaml --builder-session-id SESSION
python main.py --autopilot-build task.md --autopilot-workflow workflow.yaml
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

Copilot auto mode is the default for user-prompted automation building. The user
does not run CLI commands; the agent creates the task file, runs `--copilot-auto`,
asks the user only for active `next_question` decisions, answers with
`--copilot-answer`, then continues with `--copilot-auto SESSION`.

For fast browser URL iterations, use `--copilot-try-url` when a workflow already
exists or a known recipe can supply one. It caches selector discovery, moves
policy approval before discovery, and writes `copilot_report.json/md`.

Autopilot mode is for already-authored deterministic workflow execution. Read
`.agents/config/autopilot.yaml` and `.agents/config/agent_command_manifest.json`,
then use `--autopilot-build` to validate, preflight, run, and return JSON
artifacts without manual CLI work.

OKF maintenance is required when durable repo knowledge changes, especially
docs, workflow schema, CLI commands, skills, hooks, project layout, or
agent/copilot policy. Update `docs/okf`, then run:

```bash
python scripts/okf.py generate-indexes docs/okf
python scripts/okf.py validate docs/okf
```

Do not claim production-ready unless dry-run or one-record evidence supports it.
