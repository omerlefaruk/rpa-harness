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
  "current_stage": "string or null",
  "failed_step_id": "string",
  "failed_step_description": "string",
  "action_type": "string",
  "intended_action": "string or null",
  "expected_result": "string or null",
  "actual_result": "string or null",
  "input_record_id": "string or null",
  "target_system": "string or null",
  "error_type": "SelectorNotFoundError | VerificationFailedError | TimeoutError | ...",
  "error_message": "string",
  "error_category": "transient | permanent | unknown",
  "error_class": "transient | data | business | authorization_config | automation_defect | external_system | security_privacy | unknown",
  "retry_attempt": 1,
  "max_attempts": 2,
  "retry_allowed": false,
  "side_effect_risk": "low | medium | high | unknown",
  "human_review_required": true,
  "first_failed_stage": "string or null",
  "last_known_good_stage": "string or null",
  "escalation_status": "notified | not_configured | sent | failed | null",
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

## Rulebook Failure Fields

Failure reports include the RPA rulebook evidence contract when the runner can
derive it: current stage, intended action, expected vs actual result, target
system, retry attempt, taxonomy class, side-effect risk, and escalation status.
Absent values are serialized as `null`; raw credentials and sensitive payloads
must remain redacted.

## HTML And Bundles

Render a JSON failure report to an HTML investigation page:

```bash
python main.py --render-failure-report runs/{run_id}/failure_report.json
```

Create a portable zip containing the run directory and a redacted manifest:

```bash
python main.py --bundle-run runs/{run_id}
```

Browser selector failures may include `evidence.selector_repair`, a JSON
artifact with the failed selector, current URL, intended action, and a selector
swarm command to generate a verified replacement selector. Desktop failures may
include `evidence.uia_tree` plus window/app metadata when Windows UIAutomation
is available.
