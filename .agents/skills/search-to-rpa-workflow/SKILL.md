---
name: search-to-rpa-workflow
description: >
  Convert completed browser searches, public-site research, review collection,
  lead/list scraping, or other web data-gathering tasks into repeatable RPA
  Harness workflows/tests, then harden them with measured autoresearch. Use
  whenever a one-off search result should become reusable automation.
hooks: "preflight, compliance, validation, reporting, memory-search, memory-save"
---

# Search To RPA Workflow

## Rule

Do not leave a completed search or browser research task as a one-off answer.
Turn it into a dedicated harness artifact, then run autoresearch hardening.

## Required Flow

1. **Open RPA Memory first**
   - `GET /api/search` for similar targets, selectors, failures, and prior workflows.
   - `GET /api/timeline` around relevant matches.
   - `POST /api/observations/batch` only for selected details.
   - If memory is down, state it and continue from current repo evidence.

2. **Preserve the search contract**
   - Record target URL, query terms, filters, sort order, date window, locale, and source.
   - Define success checks before implementation.
   - If the target blocks automation, make the blocked state explicit and verifiable.

3. **Create a dedicated harness artifact**
   - Browser search or public-site extraction: create an `AutomationTestCase` in `tests/browser/`.
   - Excel or record-driven work: create an `RPAWorkflow` in `tests/rpa/` or `workflows/`.
   - Reuse `PlaywrightDriver` and the browser selector swarm instead of manual browsing.
   - Write structured output under ignored runtime paths such as `runs/` or `reports/`.
   - Include all major actions as `self.step(...)`.

4. **Use browser selector swarm**
   - Run swarm before extraction to capture selector evidence and screenshots.
   - Prefer stable selectors: test id, role/name, label, placeholder, text, id, CSS, XPath.
   - Treat `insufficient actionable page evidence`, 403 pages, captchas, and login walls as first-class outcomes.

5. **Add tests**
   - Add pure parser/date/window tests when extraction logic exists.
   - Add harness discovery or focused tests for new helpers.
   - Keep tests deterministic; do not require the public site for parser correctness.

6. **Harden with autoresearch**
   - Use a task-specific autoresearch benchmark when speed or reliability is the target.
   - The benchmark must run the new workflow/test and print a metric, for example:
     `METRIC workflow_seconds=...` or `METRIC extraction_success=...`.
   - Run:
     `python3 tools/autoresearch_runner.py --once`
   - If the default autoresearch metric does not measure this workflow, state that and run the focused benchmark/checks separately.

7. **Verify repeatability**
   - Run the exact harness command the user can reuse.
   - Example:
     `RPA_RUN_EXTERNAL_TESTS=1 RPA_HEADLESS=true python3 main.py --discover ./tests/browser --run --test-name <name> --tags external --headless --report json`
   - Report artifact paths, command results, and remaining risks.

## Done Definition

Done means:

- A repeatable harness artifact exists.
- The artifact has explicit success or blocked-state checks.
- Parser/business logic has deterministic tests.
- Browser selector swarm evidence is saved.
- Autoresearch or a task-specific benchmark was run.
- Final answer includes the reusable command and output artifact path.
