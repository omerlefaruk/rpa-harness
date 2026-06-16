# Builder Mode

Builder mode starts with evidence, not guesses.

Current minimal command:

```bash
python main.py --build-start tasks/upload_invoices.md
python main.py --capture-desktop "Legacy ERP" --capture-session-dir builder_sessions/SESSION
python main.py --discovery-validate-fixtures
```

This creates `builder_sessions/<session_id>/` with:

- `task_spec.md`
- `assumptions.md`
- `questions.json`
- `discovery_session.json`
- `workflow_draft_report.md`
- `unresolved_risks.md`

Desktop capture currently records a blocked capture package unless explicit UIA/Win32/screenshot evidence is supplied. This is deliberate: a recorder that silently invents desktop steps is worse than no recorder.

The session is only a scaffold until browser, desktop, API, or file discovery runs. Do not call a workflow production-ready until selectors, actions, success checks, and risky actions have been validated by dry-run or one-record evidence.

Builder loop:

1. Record task, inputs, outputs, secret names, and risky actions.
2. Inspect the target before drafting selectors.
3. Generate selector candidates with evidence.
4. Draft deterministic workflow phases and steps.
5. Add success checks to every step.
6. Mark side effects, retryability, and required approvals.
7. Dry-run safe phases.
8. Pause before external writes.
9. Produce a build report with unresolved risks.

Do not auto-submit, delete, pay, upload to official systems, send external messages, or solve MFA/CAPTCHA without an explicit operator gate.
