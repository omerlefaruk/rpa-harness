# Enforcement & Verification

## Before Committing

```bash
# Syntax check
python -m compileall -q harness scripts tools

# Lint (if ruff installed)
ruff check harness tests main.py
```

## Rules to Enforce

1. **No hardcoded paths**: Use YAML inputs/config variables or environment variables
2. **No hardcoded credentials**: Never commit `API_KEY`, `password`, `token`
3. **Explicit success checks**: Every executable workflow step needs success checks unless it is an allowed no-op
4. **Type hints**: Use `Optional[str]`, `dict`, `list` for public methods
5. **No `print()` in harness/**: Use `HarnessLogger`
6. **Never check in**: `reports/`, `runs/`, `screenshots/`, `data/*.xlsx`, `*.db`

## Verification Checklist

- [ ] YAML validates or audits with `main.py --validate-yaml` / `--audit-workflow`
- [ ] Run artifacts capture timeline, manifest, report, and evidence paths
- [ ] Secrets are redacted in logs, reports, prompts, and artifacts
- [ ] Screenshots/evidence are captured on failure where relevant
- [ ] Error messages include context (selector, URL, step name)
- [ ] Tests pass: `python -m pytest -q`
```
