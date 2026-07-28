# ActiveGraph workspace

This workspace is initialized for the **ActiveGraph-native** rpa-harness product.

## Layout

```text
data/                 # EventStore SQLite and local runtime data
proposals/            # Automation Proposal JSON (sample included)
evidence/             # Evidence exports
reports/              # Optional HTML/JSON reports
```

## Quick start

```bash
python main.py --automation-init-workspace .
python main.py --automation-workspace-status --automation-workspace .
python main.py --automation-validate-proposal proposals/example_read.json
python main.py --automation-register-proposal proposals/example_read.json --automation-workspace .
npx rpa-harness-agent mcp
```

YAML workflows are **not** the production runtime.
