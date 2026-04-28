You are implementing one measured RPA Harness autoresearch experiment.

Objective:
Improve RPA Harness reliability with measured, reversible changes.

Primary metric:
- capability_pass_rate (higher is better)

Allowed paths:
- tools/
- tests/
- docs/
- .autoresearch/

Rules:
- Make one small change only.
- Add or update a focused test when code changes.
- Do not touch credentials or generated reports/runs/data files.
- Do not edit protected harness/runtime paths unless a reproduced failure and test justify it.
- After editing, stop. The autoresearch runner will measure and decide keep/discard.

Recent runs:
[
  {
    "benchmark": {
      "command": "bash .autoresearch/autoresearch.sh",
      "duration_seconds": 0.549,
      "exit_code": 0,
      "tail_output": "METRIC capability_pass_rate=1\nMETRIC default_cli_seconds=0.507\n",
      "timed_out": false
    },
    "checks": {
      "command": "bash .autoresearch/autoresearch.checks.sh",
      "duration_seconds": 0.495,
      "exit_code": 0,
      "tail_output": "...................                                                      [100%]\n19 passed in 0.19s\n",
      "timed_out": false
    },
    "confidence": null,
    "direction": "higher",
    "heartbeat": [
      {
        "detail": "",
        "name": "session_files",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "memory",
        "status": "ok"
      },
      {
        "detail": "0/25",
        "name": "budget",
        "status": "ok"
      },
      {
        "detail": "Dirty files outside autoresearch scope: .agents/rules/01-core.md, .agents/rules/06-memory.md, .agents/rules/_index.md, .gitignore, AGENTS.md, SKILL.md, config/default.yaml, conftest.py",
        "name": "git_scope",
        "status": "warn"
      },
      {
        "detail": "",
        "name": "secret_scan",
        "status": "ok"
      }
    ],
    "lesson": "Accepted measured result for capability_pass_rate: 1.0",
    "metric": 1.0,
    "metric_name": "capability_pass_rate",
    "metrics": {
      "capability_pass_rate": 1.0,
      "default_cli_seconds": 0.507
    },
    "objective": "Improve RPA Harness reliability with measured, reversible changes.",
    "run": 1,
    "status": "keep",
    "timestamp": "2026-04-28T20:20:15.553436+00:00",
    "type": "run"
  }
]

Ideas:
# Autoresearch Ideas

- [ ] Improve memory retrieval scoring for `api`, `excel`, and `desktop` queries.
- [ ] Score failure report completeness against `docs/failure_report_schema.md`.
- [ ] Add a better desktop platform-boundary recommendation for macOS runs.
- [ ] Measure mocked-agent plans for required success checks and stop conditions.
- [ ] Add report/data hygiene checks for generated artifacts and redaction.

