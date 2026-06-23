# Builder Mode

Builder mode is for creating deterministic workflows from target discovery evidence. It should not guess selectors or business logic.

## Builder loop

1. Task intake: goal, target, input files, outputs, secret names, risky actions, and success criteria.
2. Target discovery: browser DOM/accessibility, API preview, desktop UIA/Win32, or legacy desktop evidence.
3. Selector/action candidates: generate scored candidates with reasons.
4. Workflow draft: phases, steps, actions, selectors, success checks, side effects, retry policy, and human gates.
5. Safe dry-run: run non-destructive phases and pause before external writes.
6. Risk review: mark weak selectors, unresolved checks, and business ambiguities.
7. One-record test: run only after approval for risky actions.
8. Promotion: keep deterministic YAML workflow and evidence.

## Builder artifacts

Builder helpers write under `builder_sessions/`:

- `task_spec.md`
- `assumptions.md`
- `questions.json`
- `discovery_session.json`
- `workflow_draft_report.md`
- `unresolved_risks.md`
- optional capture/discovery artifacts

## Commands

```bash
python main.py --build-start tasks/upload_invoices/task.md
python main.py --capture-desktop "Legacy ERP" --capture-session-dir builder_sessions/<SESSION_ID>
python main.py --discovery-validate-fixtures
python main.py --browser-selector-swarm file://$PWD/workflows/capabilities/local_browser_form.html
```

## Required behavior

- Every generated step needs success checks.
- Risky actions need approval/human gate or explicit policy.
- External writes are non-retryable by default.
- Weak legacy desktop steps must be marked weak and verified.
- Discovery failures should produce blocked results, not hallucinated coordinates.
