# Selector Strategy

Executable ladders live in `harness.automation.capabilities` (`BROWSER_SELECTOR_PRIORITY`, `DESKTOP_SELECTOR_PRIORITY`). Skills and docs must match code.

## Browser selectors

Prefer, in order:

1. `role`
2. `label`
3. `test_id`
4. `css`
5. `xpath`
6. `coordinate`

Weak strategies: `css`, `xpath`, `coordinate` (and desktop `image`). Weak fallbacks require `verified=true` (and approval when policy demands). Prefer role/label/test_id over CSS/XPath when stable alternatives exist.

## Desktop selectors

Prefer, in order:

1. `automation_id`
2. `name`
3. `class`
4. `tree_path`
5. `image`
6. `coordinate`

Coordinates must be last resort, marked verified when required, relative/calibrated when possible, and followed by explicit verification.

## Repair

Repair selectors from failure evidence, EventStore projections, screenshots, and DOM/UIA snapshots. Use ActiveGraph repair ops: propose → trial (fork) → promote. Do not auto-apply production repairs without a successful trial and promote path.
