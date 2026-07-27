# Enforcement & Verification

## Before Committing

```bash
python -m compileall -q harness scripts tools
# if ruff installed:
ruff check harness tests main.py
```

## Rules to Enforce

1. **No hardcoded credentials**: Never commit `API_KEY`, `password`, `token` values
2. **Explicit verification**: Executable actions need success/verification checks unless allowed no-op
3. **Type hints** on public methods
4. **No `print()` in harness/**: Use structured logging helpers where available
5. **Never check in**: generated reports, run exports, screenshots, local `data/*.sqlite` secrets stores

## Verification Checklist

- [ ] ActiveGraph proposal validates / registers through `AutomationApplication` or CLI
- [ ] Evidence exports and inspect projections match EventStore terminal state
- [ ] Secrets are redacted in logs, reports, prompts, and artifacts
- [ ] Screenshots/evidence captured on failure where relevant
- [ ] Error context includes selector, target, action id when available
- [ ] Tests pass: `python -m pytest -q`
- [ ] OKF (if touched): `python scripts/okf.py generate-indexes docs/okf` then `validate`
