# Browser Selector Swarm Plan

## Goal

Speed up browser automation creation by turning selector discovery into a
parallel, evidence-driven pipeline. The system should scrape rich page evidence
once, split it into small focused artifacts, let specialized subagents propose
selectors, and then prove winners through deterministic Playwright validation.

This is bounded brute force, not uncontrolled page clicking. Every candidate
must pass visibility, uniqueness, action, and success-check validation before it
can be used in a workflow.

## Principles

- Use RPA Memory before page discovery.
- Scrape broadly, but feed agents compact structured maps instead of full raw
  HTML by default.
- Prefer deterministic Playwright checks over model judgment.
- Run selector candidates in isolated browser contexts where possible.
- Never brute-force destructive actions on production state without an explicit
  safe-mode boundary.
- Store both winning and losing selector evidence so future runs avoid repeated
  work.

## Pipeline

### 1. Memory Recon

Query RPA Memory for the target domain, route, workflow name, action intent,
known selectors, failure signatures, and previous success checks.

Outputs:

- Known working selectors.
- Known failed selectors.
- Page-specific warnings.
- Existing workflow examples.

### 2. Page Stabilization

Open the target page with Playwright and wait for a stable state:

- `networkidle` or configured app-specific idle signal.
- Current URL/title captured.
- Console errors and failed network requests captured.
- Screenshot captured.

Outputs:

- Stable page state bundle.
- Browser context identifier.
- Route and title evidence.

### 3. Evidence Scraping

Create focused page maps:

- Interactive DOM map: buttons, links, inputs, selects, textareas, `[role]`,
  `[data-testid]`, `[aria-label]`, `[name]`, `[placeholder]`.
- Accessibility map: roles, accessible names, labels, descriptions.
- Form map: label-to-control relationships, input types, validation messages.
- Text map: visible headings, buttons, links, repeated table labels.
- Network map: API calls, form posts, route changes, failed requests.
- App-state map: safe public hydration data such as route params and visible
  page metadata.
- Visual map: screenshot regions and bounding boxes for visible controls.

Default rule: preserve raw HTML and screenshot as artifacts, but give subagents
the compact maps unless deeper diagnosis is required.

### 4. Parallel Candidate Generation

Dispatch specialized subagents over the maps:

- Test-id mapper proposes `data-testid`, `data-test`, and `data-qa` selectors.
- Accessibility mapper proposes `role`, `label`, and `aria-label` selectors.
- Form mapper proposes `label`, `name`, and `placeholder` selectors.
- Text mapper proposes text-based fallbacks.
- Structure mapper proposes CSS/XPath fallbacks only when higher-ranked
  strategies are missing.
- Network mapper proposes success checks based on route/API changes.
- Vision mapper proposes fallback selectors from screenshot evidence.
- Memory mapper merges previous winners and removes known failures.

Outputs:

- Candidate selectors with strategy, value, intent, confidence, and evidence.
- Candidate success checks.
- Risk flags such as destructive action, duplicate match, or dynamic selector.

### 5. Selector Tournament

Validate candidates with deterministic Playwright checks:

1. Syntax is supported by the YAML runner selector schema.
2. Candidate resolves to exactly one element unless multi-match is expected.
3. Element is visible.
4. Element is enabled or editable when required.
5. Non-mutating dry checks pass: hover, focus, text/value read.
6. Action executes in a safe context.
7. Success check passes: URL, visible text, field value, response, download,
   created file, or other workflow-specific proof.

Scoring should prioritize:

1. Proven success check.
2. Stable selector strategy.
3. Unique match.
4. Short and readable selector.
5. No dynamic tokens.
6. Prior memory success.
7. No prior memory failures.

### 6. Workflow Synthesis

The planner converts proven selectors into workflow steps. Every step must have
a success check. Generated workflows should use structured selector objects:

```yaml
selector:
  strategy: role
  role: button
  name: Login
```

Avoid raw CSS unless no better strategy is available.

### 7. Evidence Save

Store a compact observation after validation:

- Page route and intent.
- Chosen selector.
- Failed candidates.
- Success check result.
- Screenshot path or redacted artifact reference.
- Network/console warnings.

Do not store secrets, cookies, personal data, or raw credentials.

## Subagent Roles

| Role | Purpose | Output |
|---|---|---|
| `memory_recon` | Find prior selectors and failures | Memory evidence bundle |
| `page_stabilizer` | Reach stable page state | URL/title/screenshot/network summary |
| `dom_scraper` | Build compact interactive DOM map | Element inventory |
| `accessibility_mapper` | Extract role/name/label selectors | A11y candidates |
| `form_mapper` | Map labels/placeholders/names to controls | Form candidates |
| `text_mapper` | Find visible text fallbacks | Text candidates |
| `structure_mapper` | Generate CSS/XPath fallbacks | Last-resort candidates |
| `network_mapper` | Infer success checks from traffic | Success-check candidates |
| `state_mapper` | Extract safe app state metadata | Route/state hints |
| `vision_mapper` | Inspect screenshot when DOM is weak | Visual fallback candidates |
| `selector_scorer` | Merge and rank candidates | Ranked candidate list |
| `candidate_validator` | Prove candidates with Playwright | Pass/fail proof |
| `workflow_planner` | Convert proven candidates into steps | Workflow plan |
| `repair_agent` | Diagnose failed tournament/workflow runs | Patch recommendation |

## Safety Gates

- Destructive verbs such as delete, submit payment, cancel, send, approve, or
  publish require explicit safe-mode approval or a disposable test target.
- Candidate validation should prefer cloned contexts and resettable fixtures.
- The validator must stop after the first proven candidate unless configured for
  benchmark mode.
- Coordinates are allowed only as final fallback and must be marked unstable.

## Implementation Phases

### Phase 1: Offline Config and Docs

- Add the selector-swarm plan.
- Add a dedicated subagent model mapping config.
- Keep existing default config unchanged.

### Phase 2: Recon Artifacts

- Add a browser recon command that produces page maps.
- Store raw artifacts under run output directories.
- Redact sensitive values before memory writes.

### Phase 3: Candidate Tournament

- Add a validator that runs candidate selectors through deterministic
  Playwright checks.
- Return a structured proof report.
- Save winner/loser observations to RPA Memory.

### Phase 4: Workflow Generation

- Feed proven selector bundles into workflow planning.
- Generate YAML steps with success checks.
- Run the workflow end to end.

### Phase 5: Benchmark Mode

- Run multiple pages/domains.
- Measure time-to-first-proven-selector, pass rate, retry rate, and memory hit
  rate.
- Emit an HTML report.

## Open Decisions

- Whether selector candidates should be stored in SQLite only or also indexed in
  a vector store.
- Whether browser recon should run inside the current agent loop or as a
  separate CLI command.
- Whether visual fallback should use screenshots only or combine screenshot
  regions with the accessibility tree.
