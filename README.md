# RPA Harness

A hardened RPA harness for browser, API, desktop, Excel, YAML workflow, and agent-assisted automation. The project is organized around deterministic execution, evidence-rich failure reports, memory-backed learning, and autonomous self-improvement.

## Core idea

The harness can improve continuously without waiting for user input. The default autonomy profile is now free-mutation mode:

1. heartbeat detects a gap, stale artifact, failed test, open idea, or technology-source change;
2. candidate improvement is written as auditable evidence;
3. implementation happens in an isolated worktree;
4. the coding agent may change repository source, tests, docs, scripts, configs, workflows, and project metadata;
5. deterministic checks, secret scans, artifact hygiene checks, commit, fast-forward merge, post-merge checks, and push run automatically.

Free mode removes the narrow allowed-path edit boundary, but it still blocks generated artifacts, virtual environments, git internals, local databases, screenshots, logs, downloads, reports, and credential files. The result is not passive planning; it is an unattended code-changing loop with rollback and audit records.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
python -m playwright install chromium
python main.py --validate-yaml workflows/examples/search_to_rpa_workflow.yaml
python main.py --tech-radar-once
python main.py --self-improve-once
```

For a deterministic local health check:

```bash
python -m py_compile $(find harness subagents tools tests -name '*.py' -print) main.py conftest.py
pytest tests/test_security.py tests/test_artifact_hygiene.py tests/test_tech_radar.py tests/test_line_endings.py tests/test_project_metadata.py
```

## Main execution surfaces

| Surface | Command | Purpose |
| --- | --- | --- |
| Test harness | `python main.py --discover tests --run` | Discover and run Python test classes through the orchestrator. |
| YAML workflow | `python main.py --run-yaml <workflow.yaml>` | Run declarative RPA workflows with verification and failure evidence. |
| Browser selector swarm | `python main.py --browser-selector-swarm <url>` | Discover stable selectors and validate candidates. |
| Memory service | `python main.py --rpa-memory-serve` | Serve the SQLite-backed RPA memory API. |
| Dashboard | `python main.py --serve` | Serve reports and run summaries. |
| Technology radar | `python main.py --tech-radar-once` | Read authoritative sources and emit improvement candidates. |
| Self-improvement once | `python main.py --self-improve-once` | Run one free-mutation repository-scope improvement cycle. |
| Self-improvement daemon | `python main.py --self-improve-24-7` | Run the autonomous code-changing heartbeat continuously. |
| Autoresearch supervisor | `python main.py --autoresearch-supervisor-once` | Run one supervisor cycle using the configured profile. |

## Architecture

- `harness/orchestrator.py` coordinates tests, workflows, reporting, and agent runs.
- `harness/rpa/yaml_runner.py` executes declarative browser/API/desktop/Excel workflows with retries, redaction, and failure reports.
- `harness/memory/` records execution facts and provides a local or HTTP-backed memory service.
- `harness/selectors/` and `tools/browser_selector_swarm.py` harden selector discovery.
- `tools/autoresearch_runner.py` and `tools/autoresearch_supervisor.py` provide the self-improvement heartbeat, repository-scope worktree execution, optional review gates, merge controls, rollback, and push automation.
- `tools/tech_radar.py` scans configured technology sources and produces auditable improvement candidates without changing code.
- `.autoresearch/` contains the autonomous loop configuration, hooks, ideas, and technology-radar source list.
- `docs/` contains workflow, memory, verification, mutation, and continuous-improvement policy documents.

## Hardening defaults

The free profile is configured in `.autoresearch/autoresearch.sovereign.json` and is also the default supervisor profile. It uses:

- repository-scope code mutation in isolated worktrees;
- automatic commit, fast-forward merge, post-merge verification, and push when configured;
- skipped automated review by default, because unattended mutation was requested;
- secret scanning for changed text files;
- generated-artifact, virtual-environment, git-internal, local-database, screenshot, download, report, log, and credential-file blocks;
- failure evidence and technology-radar candidates as improvement inputs;
- line-ending enforcement through `.gitattributes` and tests;
- heartbeat records and JSONL audit trails.

## Technology radar

The radar source list lives at `.autoresearch/tech_radar.sources.json`. It currently watches authoritative documentation for browser automation, computer-use automation, agent tools, observability, durable workflow execution, and evaluation frameworks.

Run it manually:

```bash
python main.py --tech-radar-once
```

For heartbeat operation the hook scans one configured source per cycle by default and advances a persistent cursor, which avoids blocking the entire supervisor on a slow external documentation site. Increase `AUTORESEARCH_TECH_RADAR_SOURCES_PER_HEARTBEAT` when the network is reliable.

The radar writes generated state and candidates under `.autoresearch/`:

- `.autoresearch/tech_radar.state.json`
- `.autoresearch/tech_radar.jsonl`
- `.autoresearch/tech_radar_candidates.md`

Those files are ignored because they are runtime artifacts. The `before.sh` autoresearch hook runs the radar by default on each heartbeat. Disable it with:

```bash
AUTORESEARCH_TECH_RADAR=0 python main.py --autoresearch-supervisor-once
```

## 24/7 operation

Run the free code-changing loop directly:

```bash
python main.py --self-improve-24-7
```

Run one cycle:

```bash
python main.py --self-improve-once
```

Install as a daemon:

```bash
scripts/install_launchd_self_improvement.sh   # macOS
scripts/install_systemd_self_improvement.sh   # Linux user service
```

The scheduler scripts call `scripts/start_self_improving_daemon.sh`, which uses `.autoresearch/autoresearch.sovereign.json`. The daemon expects a working Python environment, Codex CLI or `AUTORESEARCH_AGENT_COMMAND`, git or the configured git proxy, and optional RPA Memory.

## Evaluation contract

A change should not be accepted only because it looks plausible. It should improve at least one measurable target without violating any guardrail:

- pass rate for workflows and tests;
- selector stability and recovery success rate;
- failure-report completeness;
- artifact-hygiene score;
- memory retrieval precision;
- default CLI startup latency;
- workflow execution latency;
- secret-scan cleanliness.

## Repository hygiene

Do not commit virtual environments, generated reports, run artifacts, local databases, screenshots, or `.env` files. The project includes tests for `.gitignore`, line endings, and pyproject metadata to keep the harness portable across Unix-like and Windows environments.
