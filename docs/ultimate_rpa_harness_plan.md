# Ultimate RPA Harness Plan

This plan combines the current codebase into one coherent, hardened RPA system with evidence, deterministic evaluation, audit records, and rollback.

## 1. System harmony

The harness should be treated as five connected planes:

| Plane | Current assets | Target role |
| --- | --- | --- |
| Execution | `harness/rpa/`, `harness/drivers/`, YAML workflows | Run browser, API, desktop, Excel, and document automation with retries and verification. |
| Control | `main.py`, `harness/orchestrator.py`, workflow schemas | Provide one CLI/control surface for tests, workflows, selector discovery, memory, and dashboard. |
| Evidence | reports, failure reports, screenshots, checks | Produce actionable failure records before any repair attempt. |
| Memory | `harness/memory/` | Store execution facts, tool calls, lessons, selector outcomes, and repair attempts. |
| Evaluation | `tests/`, deterministic checks, capability tests | Decide whether a change is an improvement rather than a mutation. |

Every plane should feed the next one. Failures create evidence; evidence becomes memory; memory informs repair; repairs are evaluated.

## 2. Hardened automation rules

Autonomy should be powerful but bounded:

- never merge without deterministic tests/checks;
- never commit generated artifacts unless they are intentional fixtures;
- never store secrets in memory, reports, docs, or JSONL logs;
- never patch a failure without capturing failure evidence first;
- never accept a change that only adds complexity without improving a metric.

## 3. Fast implementation path

### Phase A: immediate hardening

- enforce LF line endings and repository hygiene;
- add a project README matching `pyproject.toml`;
- add tests for metadata, artifact ignores, and line endings.

### Phase B: eval acceleration

- split tests into smoke, workflow, browser, memory, and full suites;
- record per-test runtime and failure flakiness;
- require improvement candidates to declare their expected metric impact.

### Phase C: runtime speed

- cache browser contexts and selector maps where safe;
- prefer API verification over UI verification when the UI is only a trigger;
- add workflow-level timeouts and action-level latency budgets;
- use idempotent steps and resumable checkpoints;
- isolate slow network research from local deterministic checks.

### Phase D: production durability

- run memory, dashboard, and supervisor as separate services;
- export logs/traces/metrics to an external system;
- add rollback for merged changes that degrade metrics;
- separate read-only exploratory agents from write-capable repair agents;
- require a human approval gate for dependency upgrades, credential handling, and destructive workflow actions.

## 4. Evaluation matrix

| Metric | Why it matters | Gate |
| --- | --- | --- |
| Smoke-test pass rate | Keeps heartbeat fast | Must pass before review. |
| Secret scan | Prevents credential leakage | Must pass always. |
| Artifact hygiene | Keeps repo clean | Must pass always. |
| Failure evidence completeness | Prevents blind repair | Required before workflow repair. |
| Selector stability | Reduces flaky UI automation | Must not regress on selector tasks. |
| Runtime latency | Keeps workflows fast | Must not exceed agreed budget. |
| Memory precision | Prevents bad self-learning | Must improve or remain stable. |
| Documentation freshness | Keeps operator guidance valid | Required for changed behavior. |

## 5. Operating model

Run these in production-like environments:

```bash
python main.py --rpa-memory-serve --rpa-memory-host 127.0.0.1 --rpa-memory-port 37777
python main.py --serve --port 8080
```

## 6. Definition of “bulletproof”

No RPA system is literally bulletproof because UIs, websites, credentials, networks, and dependencies change. The practical target is a system that fails safely, explains why it failed, and only repairs through explicit gates.
