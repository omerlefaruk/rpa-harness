# Workflow Specification

A workflow is a YAML file describing an automation.

## Required Top-Level Fields

```yaml
id: string
name: string
version: string
type: browser | desktop | api | excel | mixed
description: string
inputs: {}
credentials: {}
steps: []
```

## Rulebook Contract Fields

Legacy workflows remain valid without these fields, but `--audit-workflow`
reports warnings and a 0-5 readiness score when they are missing.

```yaml
owner: string
target_systems: [string]
input_schema: {}
output_destination: string
system_of_record: string
success_condition: string
safe_test_case: string
allowed_side_effects: [string]
rerun_policy: string
escalation_owner: string
```

## Step Definition

```yaml
steps:
  - id: string              # unique within workflow
    description: string     # human-readable
    current_stage: string   # business-readable stage name
    intent: string          # intended business result
    preconditions: []       # conditions checked before side effects
    postconditions: []      # expected business state after action
    proof: string           # evidence source for the postcondition
    failure_path: string    # stop/skip/escalate behavior when proof is absent
    action:
      type: string          # browser.goto, browser.click, browser.fill, api.get, desktop.click, etc.
      url: string           # optional, with ${inputs.var} or ${secrets.VAR}
      selector:
        strategy: string    # data-testid, role, label, placeholder, text, id, css, xpath, automation_id, name
        value: string
      value: string
      method: string
      path: string
      json_data: {}
    success_check:
      - type: string        # url_contains, visible_text, selector_visible, field_has_value, status_code, json_path_equals, file_exists, etc.
        value: string
        redacted: boolean   # true if value contains credential
    recovery:
      - type: retry | refresh_page | fallback | skip
        max_attempts: integer
    failure_class: transient | data | business | authorization_config | automation_defect | external_system | security_privacy | unknown
    idempotency_key: string  # required for retrying side-effecting actions
    allow_without_success_check: false  # only for no_op steps
```

Side-effecting retries are intentionally strict. Actions such as `api.post`,
`api.put`, `api.patch`, `api.delete`, submit, upload, send, create, write, or
update must declare a transient failure class and an idempotency or side-effect
guard before a retry policy is accepted.

## CLI Audit

```bash
python main.py --audit-workflow workflows/capabilities/local_browser_form.yaml
```

The audit prints JSON containing normal schema validation status plus
`rulebook_audit.score`, missing fields, warnings, fix suggestions, and
production readiness.

## Authoring Templates

Use `--new-workflow` to create a rulebook-shaped YAML starting point:

```bash
python main.py --new-workflow workflows/new_api.yaml --workflow-template api_read_write --workflow-id new_api
```

Available templates:

- `browser_login_export`
- `excel_row_loop`
- `api_read_write`
- `desktop_form_fill`
- `browser_scrape`
- `reconciliation`

## Resume Ledger

Python `RPAWorkflow` subclasses can opt into an append-only record resume ledger
by setting `config.variables["resume_ledger_path"]`. Each terminal record writes
record id, status, stage, retry metadata, external reference id, and evidence
path when provided.

```bash
python main.py --resume-ledger-status runs/resume/my_workflow.jsonl
```

## Failure Artifacts

Render a failed run into a compact HTML investigation page:

```bash
python main.py --render-failure-report runs/<run_id>/failure_report.json
```

Bundle a run directory for handoff:

```bash
python main.py --bundle-run runs/<run_id>
```

## Example — Minimal

```yaml
id: minimal_example
name: Minimal Example
version: "0.1.0"
type: browser
description: Opens example.com and verifies the page loaded.

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

  - id: verify_title
    description: Verify page title exists.
    action:
      type: browser.get_title
    success_check:
      - type: variable_has_value
        value: "Example Domain"
```

## Example — Browser Login

```yaml
id: example_login
name: Example Login
version: "0.1.0"
type: browser
description: Log into example web app and verify dashboard.

inputs:
  base_url: "https://example.com"

credentials:
  username_secret: EXAMPLE_USERNAME
  password_secret: EXAMPLE_PASSWORD

steps:
  - id: open_login
    description: Open login page.
    action:
      type: browser.goto
      url: "${inputs.base_url}/login"
    success_check:
      - type: url_contains
        value: "/login"

  - id: fill_username
    description: Fill username field.
    action:
      type: browser.fill
      selector:
        strategy: label
        value: "Username"
      value: "${secrets.EXAMPLE_USERNAME}"
    success_check:
      - type: field_has_value
        selector:
          strategy: label
          value: "Username"
        redacted: true

  - id: fill_password
    description: Fill password field.
    action:
      type: browser.fill
      selector:
        strategy: label
        value: "Password"
      value: "${secrets.EXAMPLE_PASSWORD}"
    success_check:
      - type: field_has_value
        selector:
          strategy: label
          value: "Password"
        redacted: true

  - id: submit
    description: Click sign in button.
    action:
      type: browser.click
      selector:
        strategy: role
        role: button
        name: "Sign in"
    success_check:
      - type: url_contains
        value: "/dashboard"
      - type: visible_text
        value: "Dashboard"
    recovery:
      - type: retry
        max_attempts: 2
```
