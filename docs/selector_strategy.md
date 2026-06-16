# Selector Strategy

## Browser selectors

Prefer, in order:

1. `data-testid`
2. role/name
3. label
4. placeholder
5. text
6. stable id
7. CSS
8. XPath

Avoid absolute XPath when any stable selector exists. A selector candidate should explain its strategy, score, reason, match count, visibility/enabled state when available, and validation status.

## Desktop selectors

Prefer, in order:

1. automation ID
2. name + control type
3. class + control type
4. tree path
5. image anchor
6. coordinate fallback

Coordinates must be last resort, marked weak, relative/calibrated when possible, and followed by success checks.

## Repair

Repair selectors from `selector_evidence.json`, screenshots, DOM/UIA snapshots, and failed verification. Do not auto-apply production repairs unless a candidate is validated and the operator or policy allows it.
