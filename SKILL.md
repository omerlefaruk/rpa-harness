---
name: rpa-harness
description: >
  AI-powered RPA automation harness for Playwright browser automation,
  Windows UIAutomation (desktop), API integrations, Excel-driven workflows,
  agentic AI loop, persistent memory, and web dashboard.
  Use when: automating web apps, desktop apps, writing test suites,
  running UI validations, creating RPA-style automation workflows,
  delegating to fast/powerful subagents, or searching agent memory.
---

# RPA Harness

## When to Activate

- Browser automation (Playwright — clicks, form fills, navigation, data extraction)
- Desktop automation (Windows UIAutomation — app launch, UI tree walking, element interaction)
- API integration testing (REST, GraphQL via httpx)
- RPA workflows (Excel-driven data processing with mismatch detection)
- Agentic AI execution (natural language task → autonomous execution with tools)
- Memory search (past selectors, workflows, error patterns)

## Core Architecture

```
AutomationHarness (orchestrator)
├── discovers AutomationTestCase and RPAWorkflow subclasses
├── runs setup() → run() → teardown() (tests)
├── runs setup() → get_records() → process_record() → teardown() (workflows)
├── runs plan() → observe → decide → act → verify (agent mode)
└── generates HTML/JSON reports + web dashboard

Drivers
├── PlaywrightDriver   (browser: goto, click, fill, extract, screenshot, ai_action)
├── WindowsUIDriver    (desktop: launch_app, click, type_keys, dump_tree, screenshot)
└── APIDriver          (REST: get, post, put, delete, graphql)

AI Layer
├── RPAAgent           (agent loop with tool registry and decision making)
├── VisionEngine       (screenshot analysis, element detection, state verification)
├── TaskPlanner        (task → step decomposition with dependencies)
└── AgentMemory        (short-term step history within session)

Memory (claude-mem adapted)
├── RPAMemory          (observations, selector cache, error patterns)
├── MemoryDatabase     (SQLite + FTS5)
└── MemoryServer       (FastAPI worker on port 38777)
```

## Quick Start

```bash
# Install
pip install -r requirements.txt
playwright install

# Set API key
export OPENAI_API_KEY="your-key"

# Run tests
python main.py --discover ./tests --run --report html

# Agent mode
python main.py --agent "Login to example.com and verify dashboard" --headless

# Serve dashboard
python main.py --serve --port 8080

# Memory worker
python main.py --memory-serve
```

## Writing Tests

```python
from harness import AutomationTestCase, PlaywrightDriver

class MyTest(AutomationTestCase):
    name = "my_test"
    tags = ["browser"]

    async def setup(self):
        self.driver = await PlaywrightDriver.launch(config=self.config)

    async def run(self):
        self.step("Navigate")
        await self.driver.goto("https://example.com")
        await self.driver.fill("#search", "query")
        await self.driver.click("#submit")
        self.expect(await self.driver.is_visible(".results"))

    async def teardown(self):
        if self.driver:
            await self.driver.close()
```

## Writing RPA Workflows

```python
from harness import RPAWorkflow, ExcelHandler

class MyWorkflow(RPAWorkflow):
    name = "my_rpa"
    tags = ["rpa", "excel"]

    async def setup(self):
        self.input_excel = ExcelHandler(self.config.variables["input_file"])

    def get_records(self):
        for row in self.input_excel.iter_rows(sheet="Sheet1"):
            yield {"id": row.get("ID"), "amount": row.get("Amount")}

    async def process_record(self, record):
        # ... lookup in web system ...
        return {"status": "passed"}

    async def on_mismatch(self, record, reason, details=None):
        self.output_excel.append_row(sheet="Mismatches", ...)
```

## Subagent Dispatch

When delegating, use the appropriate subagent:

| Task | Subagent | Model |
|---|---|---|
| Read files, scan directories | explorer | fast |
| Browser inspection, selector discovery | selector | fast |
| Windows UIA tree walking | uia-tree | fast |
| Task decomposition | planner | powerful |
| Memory search | memory | fast |

## CLI Reference

```bash
python main.py --discover ./tests --run --report html,json
python main.py --run --tags browser --headless
python main.py --agent "Login and verify" --headless
python main.py --run-workflows --discover-wf ./tests/rpa
python main.py --serve --port 8080
python main.py --memory-serve --port 38777
python main.py --config ./config/default.yaml --discover ./tests --run
```
