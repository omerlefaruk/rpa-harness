# rpa-harness reusable and conflicting seams

**Wayfinder ticket:** [#4 Inventory reusable and conflicting rpa-harness seams](https://github.com/omerlefaruk/rpa-harness/issues/4)  
**Researched:** 2026-07-27  
**Depends on:** [activegraph-extension-boundaries.md](./activegraph-extension-boundaries.md) (closed #3)

## Question

Which current modules, contracts, tests, artifacts, CLI/MCP surfaces, and documentation can be retained or refactored into the ActiveGraph-native product, and which assumptions conflict with the new destination?

## Executive answer

**Keep the product DNA:** verification-after-action, selector policy, redaction, failure taxonomy, evidence packages, Windows browser/desktop/API/Excel drivers, and the governed MCP allowlist pattern.

**Re-host the runtime:** everything that treats `YamlWorkflowRunner` + `runs/<id>/` as the lifecycle engine must move under ActiveGraph (packs, tools, behaviors, policies/`action_class`, SQLite EventStore, sinks).

**Retire these assumptions in design:** “YAML is the only runtime,” “run artifacts are the source of truth,” dual orchestration (YAML runner vs AI agent), env-only secrets as the final model, and authority models that ignore R0–R4.

---

## Destination vs current

| Concern | AG destination (#3) | Current rpa-harness |
| --- | --- | --- |
| Lifecycle SoT | Append-only AG event log (SQLite EventStore) | Filesystem run dirs: `timeline.jsonl` + `run_manifest.json` |
| Domain packaging | First-party pack(s) | Monolithic `harness/` + YAML workflows |
| External I/O | `@tool` only | Drivers called inside `YamlWorkflowRunner` |
| Orchestration | Behaviors on events | YAML step loop (+ parallel AI/agent loops) |
| Definition format | Pack Python + graph types; YAML = import only | YAML is the only supported runtime |
| Agent interface | MCP primary; CLI human/CI/debug | Flag CLI primary; thin MCP over CLI |
| Authority | R0–R4 + policies | Rulebook + `side_effect` strings + autopilot YAML |
| Evidence | EventSink after log accept | Direct JSON/JSONL/HTML writes into `runs/` |
| Secrets | Product edge (WCM); names only | Env / `SecretValue` redaction (policy mentions OS CM) |
| Concurrency | Single-writer run | One runner per CLI invocation |

---

## 1. Module map

### `harness/` — product runtime

| Path | Purpose |
| --- | --- |
| `harness/cli.py` | Primary argparse CLI |
| `harness/config.py` | `HarnessConfig` / model routing |
| `harness/security.py` | `SecretValue`, redaction helpers |
| `harness/product_init.py` | Consumer workspace seed from templates |
| `harness/logger.py` | Structured logging helper |
| `harness/dsl.py` | Tiny `.rpa` DSL → schema YAML compiler |
| `harness/builder.py` | File-backed builder sessions + desktop capture |
| `harness/copilot.py` / `copilot_session.py` | Operator pause gates + multi-phase builder sessions |
| `harness/autopilot.py` | Agent build/run loop over YAML runner + policy |
| `harness/benchmark.py` | Benchmark utilities |
| `harness/core/artifacts.py` | Redacted JSON/JSONL helpers + run dir ids |
| `harness/core/execution.py` | Runner-neutral step/check trace structs |
| `harness/core/ids.py` | Workflow/input id helpers |
| `harness/core/rulebook.py` | Workflow rulebook contract + audit score |
| `harness/core/time.py` | UTC ISO timestamps |
| `harness/rpa/yaml_runner.py` | **Canonical runtime today** |
| `harness/rpa/schema.py` | schema_version 2 validate/migrate/normalize |
| `harness/rpa/execution_plan.py` | Phase/for_each → deterministic plan |
| `harness/rpa/ledger.py` | Append-only resume ledger for record runs |
| `harness/rpa/excel.py` | Excel row I/O (openpyxl) |
| `harness/rpa/templates.py` | Scaffold workflow YAML |
| `harness/drivers/*` | Playwright, Windows UIA, Win32, API |
| `harness/verification/*` | Check types, validation, `CheckRunner` |
| `harness/reporting/*` | Failure reports, run inspect, evidence zip, HTML |
| `harness/selectors/*` | Priority ladder, repair, browser swarm |
| `harness/resilience/*` | Typed errors, classification, recovery helpers |
| `harness/ai/*` | LLM agent loop, tool registry, planner, vision |
| `harness/desktop/*` | Desktop AI controller, clipboard, OCR |
| `harness/notifications/*` | Optional Telegram / bot channel |
| `harness/templates/workspace/` | Consumer workspace seed |

**Note:** `harness/orchestrator.py` exists only as bytecode under `__pycache__` — not a live source module. Do not revive a parallel orchestrator.

### Other surfaces

| Path | Role |
| --- | --- |
| `packages/rpa-harness-agent/` | npm launcher (`roi-harness`): init, MCP, thin CLI |
| `tools/` | Offline analyze/propose/inspect/UIA dump/benchmark utilities |
| `scripts/okf.py` | OKF index generate/validate |
| `scripts/check_product_release.py` | Release gate checks |
| `projects/*` | Real YAML product workflows |
| `workflows/` | Shared examples and capability fixtures |
| `tests/` | pytest product seams |
| `main.py` | Shim → `harness.cli:run` |
| `runs/` | Historical run artifact tree (SoT today) |
| `docs/` + `docs/okf/` | Contracts + knowledge bundle |
| `data/rpa_memory.db` | Local SQLite memory/legacy — **not** AG EventStore |
| `DESIGN.md` | Unrelated UI brand tokens — not product architecture |

---

## 2. Retain as-is or light refactor

These map cleanly onto AG tools/behaviors/policies/sinks/product layer.

| Asset | Why it maps |
| --- | --- |
| `harness/drivers/*` | External I/O cores → `@tool` factories |
| `harness/verification/*` + `docs/verification_contract.md` | Product verification after tool results |
| `harness/security.py` | Redaction for sinks, logs, reports, MCP stdout |
| `docs/credential_policy.md` | Secret-name discipline (implement WCM edge) |
| `docs/evidence_and_repair.md` | Repair-from-evidence mindset |
| `docs/selector_strategy.md` + `harness/selectors/*` | Product selector policy |
| `harness/resilience/errors.py` | Failure taxonomy → events / `failure_kind` |
| `harness/core/rulebook.py` | Readiness metadata → pack fields / policies |
| `harness/rpa/excel.py` | Excel tools |
| `harness/rpa/execution_plan.py` | Import expansion of phases/for_each |
| `harness/rpa/ledger.py` | Resume semantics → graph/events (not second SoT) |
| `harness/reporting/*` | HTML/JSON/zip as sink-derived packages |
| `harness/product_init.py` + templates | Workspace install seed |
| MCP allowlist pattern | Shape retained; backend becomes AG app services |
| Capability tests | Prove tool+verify contracts independent of host |

---

## 3. Refactor into AG-native shape

| Current | Target shape |
| --- | --- |
| `YamlWorkflowRunner` | Behaviors for lifecycle; tools for actions; YAML import path |
| `schema.py` validate/migrate/graph | YAML **import** compiler → AG types/fixtures |
| workflow/YAML docs + schema v2 | Migration/import schema; pack types become canonical |
| `dsl.py` | Optional frontend → import intermediate |
| `timeline.jsonl` authority | AG event append; optional JSONL sink for export |
| `run_manifest.json`, `records.jsonl`, `preflight.json` | Projections / sink artifacts from log + graph |
| failure/repair/evidence packages | Generated from events + tool artifacts; repair via fork/trial/promote |
| `harness/cli.py` | Thin host over shared AG services |
| npm MCP package | Primary agent API over shared Python services (not only CLI spawn) |
| autopilot / copilot | Behaviors + AG approvals; policy → ceiling / PackPolicy |
| `harness/ai/*` tool registry | Unify with AG `@tool` + `@llm_behavior` |
| `side_effect` / rulebook enums | Map capabilities to R0–R4 `action_class` |
| Project YAML under `projects/` | Migration corpus |

---

## 4. Conflict / replace

| Conflict | Where | Why it fights destination |
| --- | --- | --- |
| **YAML-as-only-runtime** | architecture, OKF system/runtime/cli docs | Contradicts YAML = migration/import only |
| **Run artifacts as SoT** | same docs + runner writes | Dual authority vs AG event log |
| **Parallel orchestrators** | YAML runner vs `ai/agent` vs autopilot/copilot | Multiple lifecycle controllers |
| **Direct I/O in runner** | `yaml_runner` execute paths | Violates AG determinism (I/O only in tools) |
| **Secrets from env only** | runner secret load → `os.environ` | Destination: WCM product edge |
| **No R0–R4 action_class** | side_effect, autopilot external-write sets | Parallel authority model |
| **Retry of external writes** | recovery + retry-run | Must align with tool cache-on-replay + non-idempotent policy |
| **CLI as primary agent surface** | OKF CLI concept | Destination: MCP primary |
| **“No SQLite observability DB”** | architecture/OKF mantra | Wording must not ban EventStore (no *dashboard* DB ≠ no runtime log) |
| **Ghost modules** | `orchestrator` pyc-only | Do not revive |
| **Second tool authority** | `harness/ai/tools.py` | Must unify with AG tools |

---

## 5. CLI / MCP surface inventory

### Entry points

| Entry | Path | Role |
| --- | --- | --- |
| Packaged CLI | `rpa-harness = harness.cli:run` | Human/CI |
| Shim | `main.py` | Compat |
| npm bin | `roi-harness` / `rpa-harness-agent` | init + mcp + thin CLI |

### CLI groups (`harness/cli.py`)

| Group | Representative flags |
| --- | --- |
| Workspace | `--init-workspace` |
| Run YAML | `--run-yaml`, phase/pause/until/record filters, `--copilot` |
| Validate | `--preflight-yaml`, `--validate-yaml`, `--audit-workflow` |
| Schema / DSL | `--migrate-workflow`, `--workflow-graph`, `--validate-dsl`, `--compile-dsl`, `--new-workflow` |
| Runs inspect | `--runs-list/show`, `--logs-show`, `--live-tail`, `--report-open`, `--retry-run` |
| Evidence | `--render-failure-report`, `--bundle-run` |
| Selectors | `--browser-selector-swarm*`, `--repair-selector`, `--repair-approve` |
| Builder / AI | `--copilot-*`, `--autopilot-build`, `--capture-desktop`, `--desktop-ai-assist` |
| Notify | `--telegram-*` |

### MCP allowlist (`packages/rpa-harness-agent/lib/mcp-server.js`)

| MCP tool | Maps to |
| --- | --- |
| `validate_workflow` | `--validate-yaml` |
| `preflight_workflow` | `--preflight-yaml` |
| `run_workflow` | `--run-yaml` |
| `list_runs` | `--runs-list` |
| `show_run` | `--runs-show` |
| `open_report` | `--report-open` |
| `repair_selector` | `--repair-selector` |

Constraints: relative paths only; redacts `sk-*` in MCP text; **no shell tool**. Today MCP spawns CLI; destination both call shared AG-backed services.

---

## 6. Artifact contracts

### Current run directory (observed)

| Artifact | Role today |
| --- | --- |
| `run_manifest.json` | Run header / summary |
| `timeline.jsonl` | Append-only lifecycle events (authority today) |
| `logs.jsonl` | Operator logs |
| `preflight.json` | Preflight results |
| `records.jsonl` | Per-record status |
| `evidence_bundle.json` | Failure evidence index |
| `failure_report.json` | Failure taxonomy + repro metadata |
| `repair_packet.json` (+ optional `.md`) | Agent/operator repair context |
| `selector_evidence.json` | Selector candidates/validation |
| `report.json` / `report.html` | Human report |
| `workflow_resolved.redacted.yaml` | Redacted resolved workflow snapshot |
| `screenshots/`, `dom/`, `artifacts/` | Binary/text evidence blobs |

### AG mapping

| Current | Relation to AG |
| --- | --- |
| `timeline.jsonl` as **authority** | **REPLACE** as SoT → EventStore; keep format only as **sink export** |
| `run_manifest.json` | **ADAPT** as projection/export |
| `records.jsonl` | **ADAPT** as projection of record objects/events |
| Screenshots, DOM, UIA, API previews | **KEEP** on filesystem; **reference** from events/graph (no blobs in log) |
| evidence/repair/failure packages | **KEEP/ADAPT** as product packaging from sink + artifact refs |
| Dual-write timeline + AG log | **DELETE** once AG is authoritative |

**Principle:** EventSink only after accept into log; no second authority.

---

## 7. Test seams worth keeping

| Area | Paths | AG note |
| --- | --- | --- |
| Schema / validation | `test_workflow_schema.py`, capability schema edges | Becomes import validation |
| Runner integration | `test_yaml_runner_integration.py` | Port to pack behaviors+tools |
| Capability runtimes | `tests/capabilities/*` | Tool integration matrix |
| Verification | `test_verification.py` | Core product invariant |
| Security | `test_security.py` | Wrap AG logging + sinks |
| Selectors / repair | `test_selector_strategy.py`, `test_repair_loop.py`, swarm tests | Pack tools + fork/promote |
| Failure taxonomy | `test_failure_taxonomy.py` | Custom events |
| Execution plan | `test_execution_plan.py` | Import/plan builder |
| CLI entry | `test_cli_entrypoint.py` | Thin host |
| Product init | `test_product_init.py` | Install path |
| Artifact hygiene | `test_artifact_hygiene.py` | Sink writers |
| Rulebook | `test_rulebook_audit.py` | Policy metadata |
| Autopilot / copilot | related tests | Approvals + authority |
| OKF | `test_okf_bundle.py` | Update concepts with runtime |
| MCP / npm | `packages/rpa-harness-agent/test/*` | Expand carefully |
| Desktop smoke | `tests/integration/test_windows_desktop_smoke.py` | Product tools |

Optional/peripheral for AG core: Telegram, benchmark, DSL, line endings, planner unit tests.

---

## 8. Docs / OKF

### Durable (KEEP / lightly update)

- `docs/verification_contract.md`
- `docs/credential_policy.md` (add WCM as default implementation)
- `docs/evidence_and_repair.md`
- `docs/selector_strategy.md`
- `docs/failure_report_schema.md`
- `docs/mutation_protocol.md`
- `AGENTS.md` (determinism, evidence, selectors, secrets)
- `docs/research/activegraph-extension-boundaries.md`

### YAML-era / SoT assumptions (ADAPT or rewrite)

- `docs/architecture.md` — YAML-only; artifact SoT; “no SQLite observability DB”
- `docs/workflow_spec.md`, `docs/yaml_schema.md` — YAML as canonical definition
- `docs/yaml_migration.md` — needs AG import-path story
- `docs/okf/system/rpa-harness.md`, `runtime/workflow-runner.md`, `interfaces/cli.md`
- `docs/operator_workflow.md`, builder/copilot docs tied only to YAML CLI

OKF process (`scripts/okf.py`) remains valid; concept content must shift with the runtime.

---

## 9. Top 10 seams

| # | Seam | Path(s) | Rec | Rationale |
| --- | --- | --- | --- | --- |
| 1 | YAML runner as lifecycle SoT | `harness/rpa/yaml_runner.py` | **ADAPT** | Domain execute/verify → pack tools+behaviors; YAML host becomes import/compat |
| 2 | Filesystem timeline as authority | `runs/*/timeline.jsonl` | **REPLACE** | AG EventStore is SoT; JSONL only via sink export |
| 3 | Drivers | `harness/drivers/*`, `rpa/excel.py` | **KEEP** | Stable external I/O cores for `@tool` |
| 4 | Verification | `verification/*`, verification contract | **KEEP** | Product-owned success proof |
| 5 | Security redaction | `security.py`, credential policy | **ADAPT** | Keep redaction; add WCM edge |
| 6 | Schema v2 / DSL | `schema.py`, `dsl.py` | **ADAPT** | Import/compiler pipeline |
| 7 | CLI flag monolith | `harness/cli.py` | **ADAPT** | Human/CI/debug host over AG services |
| 8 | MCP bridge | `packages/rpa-harness-agent/` | **ADAPT** | Primary agent interface; shared services |
| 9 | Evidence/repair packages | `reporting/*`, `selectors/repair.py` | **ADAPT** | Sink exports + fork/trial/promote |
| 10 | Parallel AI/agent loops | `harness/ai/*`, autopilot/copilot | **ADAPT** / partial **REPLACE** | Unify on AG tools/llm_behaviors/approvals |

### Nearby

| Seam | Rec | Rationale |
| --- | --- | --- |
| side_effect / rulebook vs R0–R4 | **ADAPT** | Map to `action_class` |
| Resume ledger JSONL | **ADAPT** | Graph + events; avoid third SoT |
| Product workspace init | **KEEP** | Install root for workspace SQLite + packs |
| orchestrator pyc-only | **DELETE** | Ghost |
| Architecture/OKF YAML-only wording | **REPLACE** | Align docs with destination |

---

## 10. Suggested first-party pack split (later tickets)

| Pack / layer | Absorb from today |
| --- | --- |
| Workspace / host product | CLI, MCP services, product_init, Task Scheduler, single-writer policy |
| `rpa_browser` | Playwright, browser checks, selector swarm/repair |
| `rpa_desktop` | UIA/win32, desktop checks, OCR/clipboard, governed desktop AI |
| `rpa_excel` / `rpa_api` | Excel + HTTP tools/checks |
| `rpa_evidence` | EventSink adapters, report HTML, zip bundle, redaction |
| YAML import (compat) | schema migrate + load → graph/fixture materialization |

---

## 11. Handoffs

| Deferred question | Owner ticket |
| --- | --- |
| Ownership AG vs product for evidence, approvals, credentials | #5 |
| Domain objects/events for automation lifecycle | #6 |
| Deterministic verify + no double-write recovery | #7 |
| Credential + authority coherence | #8 |
| CLI/MCP shared application services | #9 |
| Workspace install + Task Scheduler | #10 |
| YAML import/compat lifetime | #11 |
| Vertical prototype | #12 |
| Acceptance contract | #13 |
| Final transformation specification | #14 |

---

## Decision pointer (for map #2)

> Retain drivers, verification, redaction, selector policy, evidence packaging, MCP allowlist, and capability tests. Re-host lifecycle under AG: YAML runner and filesystem timeline are no longer SoT; YAML becomes import/compat; CLI/MCP share AG-backed services; unify AI tool loops with AG tools/behaviors; map authority to R0–R4. Full inventory: `docs/research/activegraph-retention-inventory.md`.
