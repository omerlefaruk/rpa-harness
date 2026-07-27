# Operator Workflow (ActiveGraph)

Primary runtime is ActiveGraph via `AutomationApplication` and a per-workspace EventStore. Operators use terminal CLI flags and MCP tools; EventStore is lifecycle authority and evidence exports are projections.

## Recommended flow

```bash
# 1. Workspace
python main.py --automation-init-workspace .rpa-automation
python main.py --automation-workspace-status --automation-workspace .rpa-automation

# 2. Author / admit
python main.py --automation-validate-proposal proposals/example_read.json
python main.py --automation-register-proposal proposals/example_read.json --automation-workspace .rpa-automation

# 3. Writes need an approval grant first
python main.py --automation-grant-approval grant.json --automation-workspace .rpa-automation

# 4. Execute
python main.py --automation-execute-read request.json --automation-workspace .rpa-automation
python main.py --automation-execute-write request.json --automation-workspace .rpa-automation

# 5. Inspect and export
python main.py --automation-inspect RUN_ID --automation-workspace .rpa-automation
python main.py --automation-export-evidence RUN_ID --automation-workspace .rpa-automation
```

## Failure investigation

1. `inspect` the run for status, `failure_kind`, `blocked_reason`, `next_required`.
2. `export_evidence` for evidence references and filesystem exports.
3. Review selector evidence when the failure is locator-related.
4. If status is `needs_reconciliation`, use **read-only** checks then `reconcile`.
5. For selector/definition repair: `propose_repair` → `trial_repair` (fork) → `promote_repair` or reject. Never patch a live parent version.

## Agent path

```bash
npx rpa-harness-agent mcp
```

Allowlisted MCP tools map 1:1 to the same application methods as the CLI flags. See `packages/rpa-harness-agent/README.md`.

## Retired surfaces

YAML validate/run/preflight, DSL, copilot, and autopilot CLI flags are removed. Historical schema notes under `docs/workflow_spec.md` / `docs/yaml_*.md` are archive context only.
