# Core Workflow

## Default Workflow: RESEARCH → EXECUTE → VALIDATE

1. **Research**: Understand context. Read AGENTS.md, check memory for past patterns.
2. **Execute**: Implement changes following existing patterns. Use skill scripts when available.
3. **Validate**: Run tests, verify correctness, check for edge cases.

## Non-Negotiables

- **SEARCH BEFORE CREATE**: Check existing implementations first
- **VENV**: Run Python via appropriate virtual environment
- **ASYNC-FIRST**: Avoid blocking I/O in async paths
- **NO SILENT FAILURES**: Log external failures with context
- **NO SECRETS**: Never commit credentials, tokens, or API keys
- **TOOL SCRIPTS AS BLACK BOXES**: Scripts in skills/scripts/ are invoked directly, not read into context

## File Organization

```
harness/          # Core framework code ONLY
subagents/        # Subagent Python classes
tests/            # Test and workflow implementations
  browser/        # Playwright tests
  desktop/        # Windows UIA tests
  api/            # API tests
  rpa/            # RPA workflows
workflows/        # Workflow definitions
config/           # Config templates
reports/          # Generated reports (gitignored)
data/             # Input/output data (gitignored)
.agents/          # Agent skills and rules
```
