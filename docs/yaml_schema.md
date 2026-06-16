# YAML Default Schema

The default workflow schema is the phase-based YAML format with `schema_version: 2`.
Old flat workflows are legacy inputs and can be migrated, but new authoring should use this structure.

Required concepts:

- `name`, optional `id`, and `description`
- `metadata` with owner, tags, and reliability level
- `assumptions` for business-state claims that need confirmation
- `inputs` with input contracts such as Excel files and required columns
- `secrets` by name only; secret values are resolved at runtime edge
- `policies` for success checks, retry, timeout, evidence, and redaction rules
- `targets` for browser, desktop, API, or mixed systems
- `phases` containing ordered `steps`
- executable steps with `action` and `success_checks`
- optional `side_effect`, `retryable`, `idempotency_key`, and `selector_quality`
- `human_gate` steps with choices and a safe default

Every executable step must have `success_checks`. Human gates are the exception, but they must declare choices and `default_safe_action`.

Example:

```yaml
schema_version: 2
name: upload_invoices
targets:
  portal:
    type: browser
    base_url: https://vendor.example.com
phases:
  - id: login
    steps:
      - id: open_login
        target: portal
        action:
          type: browser.goto
          url: https://vendor.example.com/login
        success_checks:
          - type: url_contains
            value: /login
```

Commands:

```bash
python main.py --validate-yaml workflows/examples/default_schema_example.yaml
python main.py --preflight-yaml workflows/examples/default_schema_example.yaml
python main.py --workflow-graph workflows/examples/default_schema_example.yaml --workflow-graph-output workflow_graph.json
```
