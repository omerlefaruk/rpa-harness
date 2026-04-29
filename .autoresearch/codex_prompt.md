You are implementing one measured RPA Harness autoresearch experiment.

Objective:
Improve RPA Harness reliability with measured, reversible changes.

Primary metric:
- artifact_hygiene_score (higher is better)

Allowed paths:
- tools/
- tests/
- docs/
- harness/memory/
- harness/reporting/
- harness/rpa/
- harness/ai/
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
      "duration_seconds": 0.598,
      "exit_code": 0,
      "tail_output": "METRIC failure_report_score=14\nMETRIC default_cli_seconds=0.484\n",
      "timed_out": false
    },
    "checks": {
      "command": "bash .autoresearch/autoresearch.checks.sh",
      "duration_seconds": 0.471,
      "exit_code": 0,
      "tail_output": "....................................                                     [100%]\n36 passed in 0.22s\n",
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
        "detail": "4/25",
        "name": "budget",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "git_scope",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "secret_scan",
        "status": "ok"
      }
    ],
    "lesson": "Accepted measured result for failure_report_score: 14.0",
    "metric": 14.0,
    "metric_name": "failure_report_score",
    "metrics": {
      "default_cli_seconds": 0.484,
      "failure_report_score": 14.0
    },
    "objective": "Improve RPA Harness reliability with measured, reversible changes.",
    "run": 5,
    "status": "keep",
    "timestamp": "2026-04-29T07:46:28.857918+00:00",
    "type": "run"
  },
  {
    "benchmark": {
      "command": "bash .autoresearch/autoresearch.sh",
      "duration_seconds": 0.591,
      "exit_code": 0,
      "tail_output": "METRIC memory_retrieval_score=1\nMETRIC default_cli_seconds=0.477\n",
      "timed_out": false
    },
    "checks": {
      "command": "bash .autoresearch/autoresearch.checks.sh",
      "duration_seconds": 0.452,
      "exit_code": 0,
      "tail_output": ".....................................                                    [100%]\n37 passed in 0.22s\n",
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
        "detail": "5/25",
        "name": "budget",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "git_scope",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "secret_scan",
        "status": "ok"
      }
    ],
    "lesson": "Accepted measured result for memory_retrieval_score: 1.0",
    "metric": 1.0,
    "metric_name": "memory_retrieval_score",
    "metrics": {
      "default_cli_seconds": 0.477,
      "memory_retrieval_score": 1.0
    },
    "objective": "Improve RPA Harness reliability with measured, reversible changes.",
    "run": 6,
    "status": "keep",
    "timestamp": "2026-04-29T07:49:15.657753+00:00",
    "type": "run"
  },
  {
    "benchmark": {
      "command": "bash .autoresearch/autoresearch.sh",
      "duration_seconds": 0.791,
      "exit_code": 0,
      "tail_output": "METRIC yaml_runner_api_action_lines=26\nMETRIC default_cli_seconds=0.727\n",
      "timed_out": false
    },
    "checks": {
      "command": "bash .autoresearch/autoresearch.checks.sh",
      "duration_seconds": 0.693,
      "exit_code": 0,
      "tail_output": "...........................................                              [100%]\n43 passed in 0.35s\n",
      "timed_out": false
    },
    "confidence": null,
    "direction": "lower",
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
        "detail": "6/25",
        "name": "budget",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "git_scope",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "secret_scan",
        "status": "ok"
      }
    ],
    "lesson": "Accepted measured result for yaml_runner_api_action_lines: 26.0",
    "metric": 26.0,
    "metric_name": "yaml_runner_api_action_lines",
    "metrics": {
      "default_cli_seconds": 0.727,
      "yaml_runner_api_action_lines": 26.0
    },
    "objective": "Improve RPA Harness reliability with measured, reversible changes.",
    "run": 7,
    "status": "keep",
    "timestamp": "2026-04-29T07:51:23.192072+00:00",
    "type": "run"
  },
  {
    "benchmark": {
      "command": "bash .autoresearch/autoresearch.sh",
      "duration_seconds": 0.648,
      "exit_code": 0,
      "tail_output": "METRIC agent_plan_safety_score=1.0\nMETRIC default_cli_seconds=0.542\n",
      "timed_out": false
    },
    "checks": {
      "command": "bash .autoresearch/autoresearch.checks.sh",
      "duration_seconds": 0.563,
      "exit_code": 0,
      "tail_output": ".............................................                            [100%]\n45 passed in 0.31s\n",
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
        "detail": "7/25",
        "name": "budget",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "git_scope",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "secret_scan",
        "status": "ok"
      }
    ],
    "lesson": "Accepted measured result for agent_plan_safety_score: 1.0",
    "metric": 1.0,
    "metric_name": "agent_plan_safety_score",
    "metrics": {
      "agent_plan_safety_score": 1.0,
      "default_cli_seconds": 0.542
    },
    "objective": "Improve RPA Harness reliability with measured, reversible changes.",
    "run": 8,
    "status": "keep",
    "timestamp": "2026-04-29T07:52:52.001375+00:00",
    "type": "run"
  },
  {
    "benchmark": {
      "command": "bash .autoresearch/autoresearch.sh",
      "duration_seconds": 0.604,
      "exit_code": 0,
      "tail_output": "METRIC artifact_hygiene_score=16\nMETRIC default_cli_seconds=0.565\n",
      "timed_out": false
    },
    "checks": {
      "command": "bash .autoresearch/autoresearch.checks.sh",
      "duration_seconds": 0.557,
      "exit_code": 0,
      "tail_output": "..............................................                           [100%]\n46 passed in 0.32s\n",
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
        "detail": "8/25",
        "name": "budget",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "git_scope",
        "status": "ok"
      },
      {
        "detail": "",
        "name": "secret_scan",
        "status": "ok"
      }
    ],
    "lesson": "Accepted measured result for artifact_hygiene_score: 16.0",
    "metric": 16.0,
    "metric_name": "artifact_hygiene_score",
    "metrics": {
      "artifact_hygiene_score": 16.0,
      "default_cli_seconds": 0.565
    },
    "objective": "Improve RPA Harness reliability with measured, reversible changes.",
    "run": 9,
    "status": "keep",
    "timestamp": "2026-04-29T07:54:16.797127+00:00",
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

