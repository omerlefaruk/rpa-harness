# Issue tracker: GitHub

Issues and implementation specifications for this repository live in GitHub Issues. Use the installed `gh` CLI for all operations and infer the repository from the configured remote.

## Conventions

- Create, read, comment on, label, and close issues with `gh issue`.
- Publish implementation specifications as issues.
- Publish implementation tickets in dependency order.
- Use GitHub native issue dependencies when available; otherwise include a `Blocked by` section with issue references.
- Pull requests are not treated as a request or triage surface.

## Agent-ready work

An implementation ticket is ready to claim only when it has the `ready-for-agent` label, every issue in its `Blocked by` section is closed, and it has no assignee.
