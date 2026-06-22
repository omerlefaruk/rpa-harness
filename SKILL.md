---
name: rpa-harness
description: >
  AI-powered RPA automation harness for Playwright browser automation,
  Windows UIAutomation (desktop), API integrations, Excel-driven workflows,
  agentic AI loop, and evidence artifacts.
  Use when: automating web apps, desktop apps, writing test suites,
  running UI validations, creating RPA-style automation workflows,
  delegating to fast/powerful subagents, or inspecting run artifacts.
---

# RPA Harness

## When to Activate

- Browser automation (Playwright — clicks, form fills, navigation, data extraction)
- Desktop automation (Windows UIAutomation — app launch, UI tree walking, element interaction)
- API integration testing (REST, GraphQL via httpx)
- RPA workflows (Excel-driven data processing with mismatch detection)
- Agentic AI execution (natural language task → autonomous execution with tools)
- Evidence-backed run inspection (timeline, manifest, reports, bundles, repair packets)

## Core Architecture

```
YAML workflow runtime
├── validates workflow schema and rulebook fields
├── runs explicit browser, desktop, API, Excel, and no-op actions
├── verifies every executable step with success checks
├── writes timeline.jsonl, run_manifest.json, report.html, evidence_bundle.json, and repair_packet.json
└── supports repair, retry, preflight, audit, graph, and run-inspection commands

Drivers
├── PlaywrightDriver   (browser: goto, click, fill, extract, screenshot)
├── WindowsUIDriver    (desktop: launch_app, click, type_keys, dump_tree, screenshot)
└── APIDriver          (REST: get, post, put, delete, graphql)

AI-assisted surfaces
├── Copilot/autopilot builder sessions for drafting and repairing YAML
├── Selector swarm discovery for browser selectors
├── Desktop AI assist for governed inspect/draft/repair flows
└── Evidence-backed run inspection from local artifacts
```

## Quick Start

```bash
# Install
pip install -r requirements.txt
playwright install

# Validate and run YAML
python main.py --validate-yaml workflows/examples/default_schema_example.yaml
python main.py --preflight-yaml workflows/examples/default_schema_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml
```

## Writing YAML Workflows

```yaml
id: my_workflow
name: My Workflow
version: "0.1.0"
type: browser
description: Open a page and verify it loaded.
inputs:
  target_url: "https://example.com"
steps:
  - id: open_page
    description: Open target page.
    action:
      type: browser.goto
      url: "${inputs.target_url}"
    success_check:
      - type: url_contains
        value: "example.com"
```

## CLI Reference

```bash
python main.py --validate-yaml workflows/examples/default_schema_example.yaml
python main.py --preflight-yaml workflows/examples/default_schema_example.yaml
python main.py --run-yaml workflows/examples/minimal_example.yaml
python main.py --runs-list
python main.py --runs-show RUN_ID
```

## Subagent Dispatch

When delegating, use the appropriate subagent:

| Task | Subagent | Model |
|---|---|---|
| Read files, scan directories | explorer | fast |
| Browser inspection, selector discovery | selector | fast |
| Windows UIA tree walking | uia-tree | fast |
| Task decomposition | planner | powerful |
| Run artifact inspection | explorer | fast |
