---
name: rpa-harness
description: >
  ActiveGraph-native RPA product for browser, desktop, API, and Excel capability ports
  with EventStore lifecycle authority, MCP agent loop, and evidence exports.
  Use when: authoring Automation Proposals, validating/registering definitions,
  approval-gated writes, inspect/export evidence, reconcile, or repair forks.
---

# RPA Harness (product card)

Thin entry skill for the **ActiveGraph-native** product. Canonical authoring procedures live in:

**`.agents/skills/rpa-harness-automation-builder`**

Do not reintroduce YAML runner, DSL, or copilot loops. Enforcement stays in `harness.automation`; skills are playbooks only.

## When to activate

- Draft / validate / register Automation Proposals
- Grant approval and execute read or write via capability ports
- Inspect runs and export evidence from EventStore
- Reconcile ambiguous writes; propose / trial / promote repairs
- Browser or desktop discovery (stable selectors; weak strategies last)

## Architecture (one glance)

```text
MCP / CLI --automation-*  →  AutomationApplication  →  EventStore
                              ↓
                         capability ports (ToolResult)
                              ↓
                         drivers as adapters
```

## Quick commands

```bash
python main.py --automation-list-operations
python main.py --automation-init-workspace .rpa-automation
python main.py --automation-validate-proposal proposal.json
python main.py --automation-register-proposal proposal.json --automation-workspace .rpa-automation
python main.py --automation-inspect RUN_ID --automation-workspace .rpa-automation
npx rpa-harness-agent mcp
```

## Pointers

- Selector ladders: `.agents/skills/selector-strategies`
- Failure terminal states: `.agents/skills/error-recovery`
- Domain glossary: `CONTEXT.md`
- ADRs: `docs/adr/`
- Agent rules: `AGENTS.md`
