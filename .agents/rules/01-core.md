# Core Workflow

## Default Workflow: RESEARCH → EXECUTE → VALIDATE

1. **Research**: Read AGENTS.md, inspect prior run artifacts/selectors/failures/decisions, then inspect current files.
2. **Execute**: Implement changes following existing patterns. Use skill scripts when available.
3. **Validate**: Run tests, verify correctness, check for edge cases.

## Non-Negotiables

- **SEARCH BEFORE CREATE**: Check existing implementations first
- **EVIDENCE FIRST**: Inspect current repo state and prior run artifacts before planning, editing, running browser/desktop/API work, or retrying failures
- **VENV**: Run Python via appropriate virtual environment
- **ASYNC-FIRST**: Avoid blocking I/O in async paths
- **NO SILENT FAILURES**: Log external failures with context
- **NO SECRETS**: Never commit credentials, tokens, or API keys
- **TOOL SCRIPTS AS BLACK BOXES**: Scripts in skills/scripts/ are invoked directly, not read into context

## File Organization

```
harness/          # Core YAML runner, drivers, reporting, repair, selector code
projects/         # Project descriptors under projects/<project>/workflows/main.yaml
workflows/        # Shared workflow examples and capability fixtures
tests/            # Tests for YAML runtime, drivers, reporting, repair, and policy
config/           # Config templates
reports/          # Generated reports (gitignored)
runs/             # Run artifacts (gitignored)
data/             # Input/output data (gitignored)
.agents/          # Agent skills and rules
```
