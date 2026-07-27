# ActiveGraph workspace

This workspace is initialized for the **ActiveGraph-native** rpa-harness product.

## Layout

```text
data/                 # EventStore SQLite and local runtime data
proposals/            # Automation Proposal JSON (sample included)
evidence/             # Evidence exports
runs/                 # Optional run export projections
reports/              # Optional HTML/JSON reports
config/               # Workspace config template
.agents/config/       # Allowlisted agent command manifest
```

## Quick start

```bash
python main.py --automation-init-workspace .
python main.py --automation-workspace-status --automation-workspace .
python main.py --automation-validate-proposal proposals/example_read.json
python main.py --automation-register-proposal proposals/example_read.json --automation-workspace .
npx rpa-harness-agent mcp
```

AI agents should use allowlisted MCP tools or `.agents/config/agent_command_manifest.json` — never arbitrary shell, raw drivers, or a YAML runner.

YAML workflows are **not** the production runtime. See the repo `CONTEXT.md` and `docs/adr/ADR-0001-yaml-runtime-retired.md`.
