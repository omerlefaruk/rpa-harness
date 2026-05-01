# RPA Capability Characterization Test Plan

This plan characterizes what the harness can prove today. It is intentionally not a plain unit-test checklist: each scenario is classified as supported, partial, schema-only, unsupported, or blocked.

## Gap Implementation Plan

Completed in the first gap-fix pass:
- Central redaction now applies before JSON/HTML reporting, failure-report serialization, persistent memory observations, and short-term agent memory entries.
- Python workflow mismatch semantics are explicit: workflows fail on mismatches by default, and mismatch-report workflows must opt in with `allow_mismatches = True`.
- Selector scoring now gives stable selectors higher scores than dynamic `nth-child` and generated class selectors.
- YAML API `wait` recovery now re-executes API actions after the wait instead of rechecking stale response context.
- `StepHistoryEntry` no longer requires callers to provide an id, so `RPAAgent` step execution can use real short-term history without monkeypatching.
- `ExcelHandler` can reject missing input workbooks with `create_if_missing=False`.
- Browser YAML runtime now raises an actionable Playwright installation message when the Python package is missing.
- Playwright and Chromium are installed locally, and the local browser workflow now has opt-in pytest proof plus CLI `--run-yaml` proof.
- YAML Excel actions now execute against temp XLSX files, and desktop YAML now reaches an explicit Windows-only runtime boundary instead of failing opaquely.
- Mixed browser+API YAML workflows now have an end-to-end runtime smoke using a local browser fixture and fake API driver.
- The memory server module imports and builds a FastAPI app under the current dependency stack.
- Public-site browser examples are tagged `external`/`public-site` and excluded from default harness runs. A local deterministic browser example covers normal CLI discovery.
- Playwright browser setup has a bootstrap command: `python3 scripts/bootstrap_playwright.py`.
- `json_path_equals` now uses `jsonpath-ng` and supports wildcards, filters, and quoted keys.

Remaining implementation plan:
1. Add a Windows CI/manual proof run for desktop YAML workflows, because this macOS machine cannot execute Windows UIAutomation.
2. Decide the long-term memory architecture: keep the bundled FastAPI SQLite worker, require an external memory worker, or document both as separate modes.

## Capability Matrix

| Area | Scenario | Test file or workflow file | Proves | Expected result | Current status | Evidence produced | Design gap if any | Recommended improvement |
|---|---|---|---|---|---|---|---|---|
| A. YAML schema validation | Valid browser workflow | `tests/capabilities/test_yaml_schema_edges.py`, `workflows/capabilities/local_browser_form.yaml` | Browser YAML shape accepts stable selectors and success checks | Validation passes | supported | `VALID: local_browser_form (12 steps)` | None for schema | Keep browser schema tests as contract fixtures |
| A. YAML schema validation | Valid API workflow | `tests/capabilities/test_yaml_schema_edges.py`, `workflows/capabilities/local_api_read.yaml` | API GET workflow shape is accepted | Validation passes | supported | `VALID: local_api_read (1 steps)` | None | Keep fake API tests isolated from public network |
| A. YAML schema validation | Valid no_op workflow | `tests/capabilities/test_yaml_schema_edges.py` | Explicit no-op can be allowed without success check | Validation passes | supported | Pytest assertion | None | Preserve `allow_without_success_check` only for no-op |
| A. YAML schema validation | Invalid missing success_check | `tests/capabilities/test_yaml_schema_edges.py` | Every executable step needs checks | Validation fails with specific error | supported | Validation error text | None | Keep this as a hard gate |
| A. YAML schema validation | Invalid duplicate step id | `tests/capabilities/test_yaml_schema_edges.py` | Step IDs are unique | Validation fails | supported | Validation error text | None | None |
| A. YAML schema validation | Invalid undeclared secret reference | `tests/capabilities/test_yaml_schema_edges.py` | Secret references must be declared in credentials | Validation fails | supported | Validation error text | None | None |
| A. YAML schema validation | Invalid literal sensitive value | `tests/capabilities/test_yaml_schema_edges.py` | Sensitive keys cannot contain literal values | Validation fails | supported | Validation error text | Only catches sensitive key names, not all sensitive-looking values | Add optional value-pattern scanning for tokens/password-like literals |
| A. YAML schema validation | Invalid secret in URL/path | `tests/capabilities/test_yaml_schema_edges.py` | Secrets cannot enter URL or path fields | Validation fails | supported | Validation error text | None | None |
| A. YAML schema validation | Destructive API action without allow_destructive | `tests/capabilities/test_yaml_schema_edges.py` | API writes require workflow-level approval | Validation fails | supported | Validation error text | None | Keep destructive gate explicit |
| A. YAML schema validation | always_pass on non-no_op | `tests/capabilities/test_yaml_schema_edges.py` | `always_pass` cannot mask real actions | Validation fails | supported | Validation error text | None | None |
| A. YAML schema validation | field_has_value without selector | `tests/capabilities/test_yaml_schema_edges.py` | Browser field checks must identify the field | Validation fails | supported | Validation error text | None | None |
| B. YAML runtime: browser | Local deterministic browser workflow | `tests/capabilities/test_yaml_browser_runtime.py`, `workflows/capabilities/local_browser_form.yaml` | `goto`, `get_title`, `get_text`, `fill`, `click`, `wait_for`, `wait_for_url`, `press`, `select_option`, `check`, `uncheck` execute against local HTML | Workflow passes | supported | `RPA_RUN_INTEGRATION=1` browser tests and CLI `--run-yaml` passed locally | None | Keep Playwright install in setup/CI |
| B. YAML runtime: browser | URL/text/selector/field/variable checks | `tests/capabilities/test_yaml_browser_runtime.py` | Browser checks run against real page state | Checks pass | supported | Opt-in browser test fixture passed | None | None |
| B. YAML runtime: browser | Broken selector failure evidence | `tests/capabilities/test_yaml_browser_runtime.py` | Failure report captures screenshot, DOM, current URL | Failure report includes evidence paths | supported | Opt-in browser failure test passed | None | None |
| B. YAML runtime: browser | Secret redaction in browser results | `tests/capabilities/test_yaml_browser_runtime.py` | Filled secret does not appear in result JSON | Secret absent from serialized result/report | supported | Opt-in browser test passed | None | Keep report redaction centralized |
| C. YAML runtime: API | api.get status 200 | `tests/capabilities/test_yaml_api_runtime.py` | YAML runner executes API GET through driver | Step passes | supported | Fake APIDriver call log and step checks | None | Keep fake driver as stable local API fixture |
| C. YAML runtime: API | json_path_equals | `tests/capabilities/test_yaml_api_runtime.py`, `tests/test_verification.py`, `docs/verification_contract.md` | JSON path resolution supports dot paths, indexes, wildcards, filters, and quoted keys through `jsonpath-ng` | Check passes | supported | Step check result plus parser feature tests | None | Keep dependency pinned in project requirements |
| C. YAML runtime: API | response_contains | `tests/capabilities/test_yaml_api_runtime.py` | Response body substring checks work | Check passes | supported | Step check result | Raw response body is used internally | Ensure redaction before any reporting surface |
| C. YAML runtime: API | api.post with allow_destructive | `tests/capabilities/test_yaml_api_runtime.py`, `workflows/capabilities/local_api_write.yaml` | Approved write actions execute and are marked destructive | Step passes | supported | Fake driver call log, `destructive: true` | None | Keep write workflows local/fake in CI |
| C. YAML runtime: API | Missing secret preflight | `tests/capabilities/test_yaml_api_runtime.py` | Missing env secret fails before execution | Config failure, no API calls | supported | `missing_secrets`, empty call log | None | None |
| C. YAML runtime: API | Authorization header redaction | `tests/capabilities/test_yaml_api_runtime.py` | Secret reaches driver but not result JSON | Driver sees header, result omits secret | supported | Serialized result check | None in YAML result path | Extend same redaction to all reports |
| C. YAML runtime: API | Query string sanitized in evidence | `tests/capabilities/test_yaml_api_runtime.py` | API evidence strips query and redacts headers/body | Failure artifact has clean URL and redacted values | supported | `api_response.json` artifact | None | None |
| C. YAML runtime: API | API 500 failure report | `tests/capabilities/test_yaml_api_runtime.py` | Failed check creates failure report and API response artifact | Workflow fails with report path | supported | `failure_report.json`, `api_response.json` | None | Add schema validation for artifact fields |
| D. YAML runtime: mixed/desktop/excel | Mixed browser+api runtime | `tests/capabilities/test_yaml_schema_edges.py`, `tests/capabilities/test_yaml_browser_runtime.py` | Mixed workflow can contain and execute browser and API actions | Validation and runtime pass | supported | Schema assertion plus `RPA_RUN_INTEGRATION=1` mixed runtime smoke passed | None | Keep fake API mixed smoke deterministic |
| D. YAML runtime: mixed/desktop/excel | Desktop YAML runtime | `tests/capabilities/test_yaml_schema_edges.py` | Desktop actions route to Windows UIAutomation driver | Non-Windows run fails with explicit platform message | partial | `failure_type: execution`, platform message | Windows UIA cannot be proven on macOS | Run desktop workflow on Windows CI/manual host |
| D. YAML runtime: mixed/desktop/excel | Excel YAML runtime | `tests/capabilities/test_yaml_excel_desktop_runtime.py` | `excel.write`, `excel.append_row`, and `excel.read` execute against temp XLSX | Workflow passes | supported | Workbook/cell verification checks passed | None | None |
| E. AutomationTestCase | Discovery | `tests/capabilities/test_harness_discovery.py` | `AutomationHarness` discovers subclasses from files | Discovered class list matches | supported | Pytest assertion | Import failures are warnings, not hard failures | Add optional strict discovery mode |
| E. AutomationTestCase | Tags filter | `tests/capabilities/test_harness_discovery.py` | Tag filter selects matching tests | Only tagged test runs | supported | Result names and event log | None | None |
| E. AutomationTestCase | Test-name filter | `tests/capabilities/test_harness_discovery.py` | Name filter selects exact test | Only named test runs | supported | Result names and event log | None | None |
| E. AutomationTestCase | Lifecycle order | `tests/capabilities/test_harness_discovery.py` | `setup -> run -> teardown` executes normally | Ordered events and step logs | supported | Logs `Step 1`, `Step 2` | None | None |
| E. AutomationTestCase | Teardown error handling | `tests/capabilities/test_harness_discovery.py` | Teardown errors do not hide run failure | Original error preserved, teardown logged | supported | Result error/logs | Teardown failure does not affect status if test passed | Consider marking passed test as warning/error when teardown fails |
| E. AutomationTestCase | Screenshot attachment | `tests/capabilities/test_harness_discovery.py` | Screenshots can be attached to `TestResult` | Path appears in result | supported | Result screenshot list | No file validation | Optionally verify attachment existence before reporting |
| F. Python RPAWorkflow | Zero records | `tests/capabilities/test_rpa_workflow_capabilities.py` | Empty input is handled | Workflow passes with zero counts | supported | WorkflowResult counts | Ambiguous whether zero records should pass in all domains | Add per-workflow policy for empty input |
| F. Python RPAWorkflow | All records pass | `tests/capabilities/test_rpa_workflow_capabilities.py` | Success records and `on_success` work | Workflow passes, processed count increments | supported | WorkflowResult counts | None | None |
| F. Python RPAWorkflow | One pass and one mismatch | `tests/capabilities/test_rpa_workflow_capabilities.py` | Mismatch flow calls `on_mismatch` and writes output | Strict workflow fails by default; mismatch-report workflow passes only with `allow_mismatches = True` | supported | Output workbook and counts | Resolved by explicit mismatch policy | Use `allow_mismatches = True` only for workflows where mismatches are intended business output |
| F. Python RPAWorkflow | Skipped record | `tests/capabilities/test_rpa_workflow_capabilities.py` | Skips are counted separately | Workflow passes, skipped count increments | supported | WorkflowResult counts | None | None |
| F. Python RPAWorkflow | Retry succeeds second attempt | `tests/capabilities/test_rpa_workflow_capabilities.py` | Retryable record uses shared retry | Processed after retry | supported | Calls and retry count | None | None |
| F. Python RPAWorkflow | Retry exhausts attempts | `tests/capabilities/test_rpa_workflow_capabilities.py` | Exhausted retry fails when no records pass | Workflow fails | supported | Calls, retry count, failed count | None | None |
| F. Python RPAWorkflow | Output files | `tests/capabilities/test_rpa_workflow_capabilities.py` | Workflow records generated artifacts | `output_files` contains workbook | supported | WorkflowResult output_files | None | None |
| G. Excel/data-driven RPA | Read input rows | `tests/capabilities/test_rpa_workflow_capabilities.py` | Temp XLSX rows can be loaded | Two records processed | supported | WorkflowResult total_records | None | None |
| G. Excel/data-driven RPA | Normalize empty/missing values | `tests/capabilities/test_rpa_workflow_capabilities.py` | Workflow can normalize `None` and blanks | Empty values become empty strings | supported | Workflow record data | No shared normalization helper | Add small reusable data normalization utility |
| G. Excel/data-driven RPA | Compare expected vs actual | `tests/capabilities/test_rpa_workflow_capabilities.py` | Decision logic separates comparison result from action/output | One pass, one mismatch | supported | Counts and mismatch row | None | None |
| G. Excel/data-driven RPA | Write mismatches workbook | `tests/capabilities/test_rpa_workflow_capabilities.py` | Mismatch workbook is generated | XLSX contains expected row | supported | Temp workbook cells | None | None |
| G. Excel/data-driven RPA | workbook_exists/sheet_exists/cell_equals | `tests/capabilities/test_rpa_workflow_capabilities.py` | Excel verification checks work against temp workbook | All checks pass | supported | CheckRunner results | None | None |
| G. Excel/data-driven RPA | Missing input file | `tests/capabilities/test_rpa_workflow_capabilities.py` | Strict workflow can fail predictably | Workflow fails with clear error and `ExcelHandler(create_if_missing=False)` rejects missing inputs | supported | WorkflowResult error_message, direct ExcelHandler assertion | None | Use `create_if_missing=False` for input workbooks |
| H. Selector strategy/healing | Priority favors data-testid | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Strategy table starts with stable selectors | Assertion passes | supported | Pytest assertion | None | Keep scorer aligned with strategy table |
| H. Selector strategy/healing | Dynamic selectors identified | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | nth-child/generated classes are detected | Assertion passes | supported | Pytest assertion | None | None |
| H. Selector strategy/healing | Healing ladder alternatives | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Broken ID creates data-testid/name alternatives before XPath fallback | Assertion passes | supported | Ladder assertions | Alternatives are string heuristics only | Add DOM-aware selector proposal scoring |
| H. Selector strategy/healing | Dynamic selectors score worse | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Stable selectors score above nth-child/generated class | Assertion passes | supported | Pytest assertion | None | Keep score rules aligned with selector priority ladder |
| H. Selector strategy/healing | Broken selector repair evidence | `tests/capabilities/test_yaml_browser_runtime.py` | Browser failure report gives screenshot/DOM/URL | Failure report includes repair evidence | supported | Opt-in browser failure report passed | None | None |
| I. Recovery/retry | YAML retry recovery | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Retry re-executes after failed check | Passes on second fake API response | supported | Attempts = 2, calls = 2 | None | None |
| I. Recovery/retry | YAML wait recovery | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Wait should re-evaluate transient API state | Passes on second fake API response after wait | supported | Attempts = 2, calls = 2 | None for API wait recovery | Keep browser wait as recheck-only unless action re-execution is explicitly requested |
| I. Recovery/retry | refresh_page recovery | `tests/capabilities/test_yaml_browser_runtime.py` | Browser page reload path reloads and retries the action | Passes on second attempt | supported | Attempts = 2 in opt-in browser test | None | None |
| I. Recovery/retry | smart_retry transient | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Transient errors retry then pass | Assertion passes | supported | Call count = 2 | None | None |
| I. Recovery/retry | Permanent validation not retried | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Permanent errors fail once | Assertion passes | supported | Call count = 1 | None | None |
| I. Recovery/retry | Circuit breaker deterministic | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Breaker opens after threshold | Assertion passes | supported | Open error raised | None | None |
| J. Memory/AI layer | Evidence-style memory search | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Memory search returns relevant observation records | Assertion passes | supported | Search result | None | None |
| J. Memory/AI layer | Secret values excluded from memory | `tests/capabilities/test_recovery_selector_memory_capabilities.py`, `tests/test_memory.py` | Memory recorder redacts raw secret-like output before persistent write | Assertion passes | supported | Fake client payload excludes fixture secret and auth header | None | Keep memory ingestion redaction centralized |
| J. Memory/AI layer | RPAAgent mocked tools | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Agent step can execute mocked tool without LLM | Assertion passes with real short-term memory | supported | Step result | None | None |
| J. Memory/AI layer | Transient tool failure retries | `tests/capabilities/test_recovery_selector_memory_capabilities.py` | Agent retries transient tool failure and succeeds | Assertion passes | supported | Calls = 2, retries = 1 | None | None |
| K. Reporting/CLI | `--validate-yaml` | `workflows/capabilities/*.yaml` | CLI validates workflow files | Browser/API read/API write validate | supported | CLI `VALID` output | None | None |
| K. Reporting/CLI | `--run-yaml local_browser_form` | `workflows/capabilities/local_browser_form.yaml` | CLI can run real browser workflow | Passes locally | supported | CLI run passed all 12 steps | None | None |
| K. Reporting/CLI | `--discover ./tests --run --report html,json` | Existing tests plus capability tests | CLI can discover/run tests and write reports without public-site dependency | Passes locally | supported | CLI run passes deterministic local browser example by default | External public-site examples require `--tags external` or `RPA_RUN_EXTERNAL_TESTS=1` | Keep public-site tests opt-in |
| K. Reporting/CLI | `--run-workflows --discover-wf ./tests/rpa --report html,json` | `tests/rpa/example_verification.py` | Python workflow discovery/reporting | Passes locally | supported | CLI workflow run processed 2 records | Example still writes ignored report/data artifacts | Use temp-path fixtures for stricter CI proof |
| K. Reporting/CLI | Reports include metadata | `tests/capabilities/test_reporting_evidence.py` | JSON reports include test and workflow metadata | Assertion passes | supported | JSON report in temp dir | None | None |
| K. Reporting/CLI | Failure report includes repro_command | `tests/capabilities/test_reporting_evidence.py`, API failure tests | Failure reports are actionable | Assertion passes | supported | `failure_report.json` | None | Add command with `--headless --no-vision` when applicable |
| K. Reporting/CLI | Reports do not leak secrets | `tests/capabilities/test_reporting_evidence.py` | Reporter redacts arbitrary secret-like logs | Assertion passes | supported | JSON report excludes fixture secret | None | Keep redaction before serialization |

## Test Scenario List

A. YAML schema validation:
- Validate browser, API, and explicitly allowed no-op workflows.
- Reject missing `success_check`, duplicate step IDs, undeclared secrets, literal sensitive values, secrets in URL/path, destructive API actions without `allow_destructive`, `always_pass` on non-no-op actions, and `field_has_value` without a selector.

B. YAML runtime browser:
- Run a local HTML fixture with stable selectors only.
- Exercise browser actions and browser/generic success checks.
- Verify broken selector failure evidence and secret redaction.
- Browser runtime proof now runs locally when `RPA_RUN_INTEGRATION=1` is set.

C. YAML runtime API:
- Use a fake `APIDriver` for deterministic `api.get` and `api.post`.
- Verify status, JSONPath parser features, response body, secret preflight, redaction, query sanitization, and API failure evidence.

D. Mixed, desktop, excel YAML runtime:
- Validate and execute a mixed browser/API workflow with a local browser fixture and fake API.
- Verify Excel YAML execution against temp XLSX files.
- Verify desktop YAML reaches the runtime boundary and reports the non-Windows platform blocker on this machine.

E. Python `AutomationTestCase`:
- Verify discovery, tags/name filtering, lifecycle, teardown failure logging, screenshot attachment, and step log order.

F. Python `RPAWorkflow`:
- Verify zero records, all pass, mismatch output, skipped records, retry success, retry exhaustion, and output artifact tracking.
- Document current mismatch status semantics.

G. Excel/data-driven RPA:
- Use temp XLSX files only.
- Verify row reads, normalization, comparisons, mismatch workbook writing, workbook/sheet/cell checks, and missing input behavior.

H. Selector strategy/healing:
- Verify selector priority table, dynamic selector detection, healing ladder alternatives, and stable-vs-dynamic scoring.

I. Recovery/retry:
- Verify YAML retry, YAML wait recovery, `smart_retry`, permanent validation behavior, and circuit breaker determinism.
- Browser `refresh_page` recovery is covered by an opt-in Playwright test.

J. Memory and AI:
- Keep LLM calls mocked.
- Verify memory search, memory redaction before persistence, mocked agent tool execution, and transient tool retry.

K. Reporting and CLI:
- Verify YAML validation, JSON report metadata, failure report repro commands, and report redaction.
- CLI browser run is covered by a deterministic local browser example. Public-site browser examples are opt-in external tests.

## Fixtures Needed

- `workflows/capabilities/local_browser_form.html`: local deterministic browser page.
- `workflows/capabilities/local_browser_form.yaml`: browser runtime workflow against the local fixture.
- `workflows/capabilities/local_api_read.yaml`: API read workflow shape for fake/local API.
- `workflows/capabilities/local_api_write.yaml`: destructive-approved API write workflow shape for fake/local API.
- Fake API drivers in `tests/capabilities/test_yaml_api_runtime.py` and `tests/capabilities/test_recovery_selector_memory_capabilities.py`.
- Temp XLSX workbooks generated in `tests/capabilities/test_rpa_workflow_capabilities.py`.
- Temp SQLite memory DBs generated under pytest `tmp_path`.
- Temp report/run directories generated under pytest `tmp_path`.

Generated reports, screenshots, runs, data files, and XLSX outputs must remain in ignored locations or pytest temp directories.

## Commands To Run

Primary verification:

```bash
python3 scripts/bootstrap_playwright.py --check
python3 -m py_compile harness/*.py harness/**/*.py main.py
python3 -m pytest -q
RPA_RUN_INTEGRATION=1 python3 -m pytest -q tests/test_yaml_runner_integration.py
python3 main.py --validate-yaml workflows/capabilities/local_browser_form.yaml
python3 main.py --run-yaml workflows/capabilities/local_browser_form.yaml --headless --no-vision
```

Additional capability-focused commands:

```bash
python3 -m pytest -q tests/capabilities
python3 main.py --validate-yaml workflows/capabilities/local_api_read.yaml
python3 main.py --validate-yaml workflows/capabilities/local_api_write.yaml
RPA_RUN_INTEGRATION=1 python3 -m pytest -q tests/capabilities/test_yaml_browser_runtime.py
python3 main.py --discover ./tests --run --report html,json --headless --no-vision
python3 main.py --discover ./tests --run --tags external --report html,json --headless --no-vision
python3 main.py --run-workflows --discover-wf ./tests/rpa --report html,json
```

Use `python3 -m pytest` if the `pytest` executable is not installed on `PATH`.

## Known Gaps Discovered

1. Desktop YAML runtime cannot be fully proven on this macOS machine because it requires Windows UIAutomation.
2. Memory now has both an HTTP client contract and a bundled FastAPI SQLite worker. Both import and test, but the intended deployment mode should be made explicit.
3. Public-site browser examples still depend on external websites by design, but they are now opt-in and no longer part of the default CLI proof.

## Recommended Design Improvements Ranked By Impact

1. Add a Windows runner or manual Windows proof for desktop YAML workflows.
2. Make the memory deployment model explicit: bundled local worker, external worker, or both with separate docs and health checks.
3. Add CI coverage that runs `python3 scripts/bootstrap_playwright.py` before browser integration tests.
4. Add Windows desktop YAML proof once a Windows runner is available.
5. Revisit JSONPath only if real workflows need custom comparison modes beyond equality.
