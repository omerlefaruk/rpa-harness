# Failure Report Schema

Every failed workflow run produces a failure report with evidence.

## Output Location

```
runs/{run_id}/
├── failure_report.json
├── logs.jsonl
├── screenshots/
├── dom/
└── artifacts/
```

## failure_report.json Schema

```json
{
  "workflow_id": "string",
  "workflow_name": "string",
  "run_id": "string (ISO timestamp)",
  "status": "failed",
  "failed_step_id": "string",
  "failed_step_description": "string",
  "action_type": "string",
  "error_type": "SelectorNotFoundError | VerificationFailedError | TimeoutError | ...",
  "error_message": "string",
  "error_category": "transient | permanent | unknown",
  "last_successful_step": "step_id or null",
  "verification_failures": [
    {
      "check_type": "url_contains",
      "expected": "/dashboard",
      "actual": "/login",
      "message": "URL did not contain expected path"
    }
  ],
  "evidence": {
    "screenshot": "screenshots/failure_2026-04-26T12-00-00.png",
    "dom_snapshot": "dom/snapshot_2026-04-26T12-00-00.html",
    "console_logs": "artifacts/console.jsonl",
    "network_logs": "artifacts/network.jsonl",
    "current_url": "https://example.com/login",
    "artifact_paths": ["path/to/additional/evidence"]
  },
  "suspected_causes": [
    "selector changed since last run",
    "page didn't load in time",
    "credential invalid"
  ],
  "recommended_patch": null,
  "repro_command": "python -m harness.cli run workflows/examples/example_login.yaml --from-step login_submit",
  "timestamp": "2026-04-26T12:00:00Z",
  "duration_ms": 4523.0
}
```

## logs.jsonl

```jsonl
{"timestamp":"...","level":"INFO","step":"open_login","message":"Navigating to https://example.com/login"}
{"timestamp":"...","level":"INFO","step":"fill_username","message":"Filled username field"}
{"timestamp":"...","level":"ERROR","step":"submit","message":"Click failed: Selector 'button:has-text(\"Sign in\")' not found"}
```

## Evidence Requirements

| Category | Always | On Failure |
|----------|--------|------------|
| Screenshot | Optional | Required |
| DOM snapshot | No | Required (browser) |
| Console logs | No | Recommended (browser) |
| Network logs | No | Recommended (browser) |
| Current URL | No | Required (browser) |
| UIA tree snapshot | No | Required (desktop) |
| API response | No | Required (API) |
| Row id | No | Required (Excel) |
