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

## Step Definition

```yaml
steps:
  - id: string              # unique within workflow
    description: string     # human-readable
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
    allow_without_success_check: false  # only for no_op steps
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
