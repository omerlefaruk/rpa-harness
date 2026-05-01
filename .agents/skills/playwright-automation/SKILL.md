---
name: playwright-automation
description: >
  Playwright browser automation for RPA. Reconnaissance-then-action pattern:
  navigate to page, wait for stability, inspect DOM, discover selectors,
  then execute actions. Use when automating web apps, finding selectors,
  testing forms, or extracting data from web pages.
hooks: "preflight, compliance, validation, reporting, memory-save, memory-search"
---

# Playwright Automation

## Reconnaissance-Then-Action Pattern

1. **Navigate + wait**: Always wait for `networkidle` before inspection
2. **Discover selectors**: Screenshot + `page.content()` to find stable selectors
3. **Execute actions**: Use discovered selectors with auto-healing fallback

## Selector Priority Ladder

```
data-testid > aria-label > name > id > :has-text() > CSS class
```

## Anti-Patterns

- Don't use `nth-child`, `:first`, dynamic IDs
- Don't hardcode `time.sleep()` — use `wait_for_selector()` or `wait_for_load_state()`
- Don't ignore auto-healing — enable `auto_heal_selectors: true`

## Scripts

- `scripts/discover_selectors.py` — Navigate + screenshot + extract all interactive elements
- `scripts/snapshot_dom.py` — Capture full DOM for analysis
- `scripts/wait_for_stable.py` — Wait for network idle + no DOM mutations
