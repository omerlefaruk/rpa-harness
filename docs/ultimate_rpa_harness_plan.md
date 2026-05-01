# Ultimate RPA Harness Plan

This plan combines the current codebase into one coherent, hardened, self-improving system. The target is free repository-scope code mutation with evidence, worktree isolation, deterministic evaluation, audit records, and rollback.

## 1. System harmony

The harness should be treated as seven connected planes:

| Plane | Current assets | Target role |
| --- | --- | --- |
| Execution | `harness/rpa/`, `harness/drivers/`, YAML workflows | Run browser, API, desktop, Excel, and document automation with retries and verification. |
| Control | `main.py`, `harness/orchestrator.py`, workflow schemas | Provide one CLI/control surface for tests, workflows, selector discovery, memory, dashboard, radar, and supervisor. |
| Evidence | reports, failure reports, screenshots, checks | Produce actionable failure records before any repair attempt. |
| Memory | `harness/memory/` | Store execution facts, tool calls, lessons, selector outcomes, and repair attempts. |
| Evaluation | `tests/`, deterministic checks, capability tests | Decide whether a change is an improvement rather than a mutation. |
| Autoresearch | `tools/autoresearch_*`, `.autoresearch/` | Generate, implement, evaluate, commit, merge, and push repository-scope improvements in isolated worktrees. |
| Technology radar | `tools/tech_radar.py` | Watch new automation/eval/observability tooling and convert changes into reviewable candidates. |

Every plane should feed the next one. Failures create evidence; evidence becomes memory; memory and source changes become candidates; candidates become isolated patches; patches are evaluated; accepted patches update docs and workflows.

## 2. Heartbeat contract

A heartbeat should run this sequence:

1. collect recent failures, open ideas, stale docs, artifact hygiene status, and technology-radar changes;
2. choose one narrow improvement candidate;
3. create an isolated worktree;
4. patch any repository source, test, docs, scripts, workflow, config, or project metadata path needed for the chosen improvement;
5. run deterministic checks;
6. record all decisions as JSONL;
7. skip automated review in the free profile unless `require_review=true`;
8. commit, tag, fast-forward merge, and run post-merge checks;
9. push when configured and remote freshness allows it.

The heartbeat is allowed to change code without user input, while generated artifacts, credential files, git internals, virtual environments, local databases, logs, reports, downloads, and screenshots remain blocked.

## 3. Technology radar loop

The radar watches official or high-signal sources. It hashes content, detects changes, extracts titles, writes JSONL events, and appends candidate ideas. It does not install packages, rewrite dependencies, or change code. Adoption happens only through the normal supervisor gates. For unattended heartbeats, it should scan a small rotating slice of sources per run so a slow external site cannot stall the entire improvement loop.

Recommended source classes:

- browser automation: Playwright, Playwright MCP, Selenium, browser-driver release notes;
- computer-use automation: official OpenAI computer-use guidance and UI safety practices;
- durable workflow execution: Temporal and similar workflow runtimes;
- observability: OpenTelemetry, logging, tracing, metrics exporters;
- evaluation: Inspect AI, DeepEval, pytest plugins, benchmark harnesses;
- security: dependency scanning, secret scanning, sandboxing, supply-chain hardening.

## 4. Hardened autonomy rules

Autonomy should be powerful but bounded:

- never edit production code directly from a live workflow run; use an isolated worktree;
- never merge without deterministic tests/checks;
- free mode removes narrow allowed-path enforcement but keeps forbidden-path and secret gates;
- never commit generated artifacts unless they are intentional fixtures;
- never store secrets in memory, reports, docs, or JSONL logs;
- never patch a failure without capturing failure evidence first;
- never accept a change that only adds complexity without improving a metric.

## 5. Fast implementation path

### Phase A: immediate hardening

- enforce LF line endings and repository hygiene;
- add a project README matching `pyproject.toml`;
- expose `--tech-radar-once` in the CLI;
- wire the radar into `.autoresearch/autoresearch.hooks/before.sh`;
- add tests for radar behavior, metadata, artifact ignores, and line endings.

### Phase B: eval acceleration

- split tests into smoke, workflow, browser, memory, and full suites;
- add a `--suite smoke` or Makefile target for fast autoresearch cycles;
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

## 6. Evaluation matrix

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

## 7. Operating model

Run these in production-like environments:

```bash
python main.py --rpa-memory-serve --rpa-memory-host 127.0.0.1 --rpa-memory-port 37777
python main.py --serve --port 8080
python main.py --autoresearch-supervisor
```

Use a scheduler for heartbeat cadence. Keep generated `.autoresearch/tech_radar.*` files out of git and archive them externally if long-term audit history is required.

## 8. Definition of “bulletproof”

No RPA system is literally bulletproof because UIs, websites, credentials, networks, and dependencies change. The practical target is a system that fails safely, explains why it failed, repairs itself only through gates, and improves measurable outcomes over time.
