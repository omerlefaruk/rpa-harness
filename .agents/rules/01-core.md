# Core Workflow

## Default Workflow: RESEARCH → EXECUTE → VALIDATE

1. **Research**: Read `AGENTS.md` / `CONTEXT.md`, inspect EventStore run summaries and evidence exports, then inspect current files.
2. **Execute**: Implement the smallest change following existing ActiveGraph patterns. Use skill scripts for discovery when available.
3. **Validate**: Run tests, verify correctness, check edge cases. For OKF edits: generate-indexes then validate.

## Non-Negotiables

- **SEARCH BEFORE CREATE**: Check existing implementations first
- **EVIDENCE FIRST**: Inspect EventStore projections and evidence exports before planning, editing, or retrying
- **VENV**: Run Python via the appropriate virtual environment
- **NO SILENT FAILURES**: Surface external failures with context
- **NO SECRETS**: Never commit credentials, tokens, or API keys
- **TOOL SCRIPTS AS BLACK BOXES**: Scripts under `.agents/skills/*/scripts/` are invoked directly, not read into context
- **NO PARALLEL RUNTIME**: Do not reintroduce YAML runner, copilot, or DSL entrypoints

## File Organization

```
harness/automation/   # AutomationApplication, EventStore binding, capabilities, ops
harness/drivers/      # Playwright, Windows UIA, API adapters (ToolResult only)
harness/reporting/    # Evidence export helpers / HTML reports
harness/verification/ # Success-check helpers used by capability ports
packages/rpa-harness-agent/  # MCP/CLI agent launcher
tests/                # pytest (ActiveGraph contracts + drivers)
data/                 # Workspace EventStore SQLite (per workspace)
.agents/              # Agent rules, skills, command manifest
docs/okf/             # Indexed durable knowledge (OKF)
docs/adr/             # Architecture decisions
CONTEXT.md            # Domain glossary
```
