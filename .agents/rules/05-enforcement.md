# Enforcement & Verification

## Before Committing

```bash
# Syntax check
python3 -m py_compile harness/*.py harness/**/*.py main.py conftest.py

# Lint (if ruff installed)
ruff check harness/ tests/ subagents/ main.py
```

## Rules to Enforce

1. **No hardcoded paths**: Use `config.variables` or environment variables
2. **No hardcoded credentials**: Never commit `API_KEY`, `password`, `token`
3. **Async lifecycle**: `setup()`, `run()`, `teardown()` must be async
4. **Type hints**: Use `Optional[str]`, `dict`, `list` for public methods
5. **No `print()` in harness/**: Use `HarnessLogger`
6. **Never check in**: `reports/`, `screenshots/`, `data/*.xlsx`, `*.db`

## Verification Checklist

- [ ] All lifecycle methods are async
- [ ] Teardown always closes drivers and connections
- [ ] Screenshots captured on failure when `screenshot_on_failure=True`
- [ ] Error messages include context (selector, URL, step name)
- [ ] Memory observations captured for each step
- [ ] Tests pass: `python -m pytest tests/ -v`
