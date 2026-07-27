# ActiveGraph supported extension boundaries

**Wayfinder ticket:** [#3 Establish ActiveGraph supported extension boundaries](https://github.com/Rau1211/rpa-harness/issues/3)  
**Researched:** 2026-07-27  
**ActiveGraph version under review:** **v1.10.0** (Apache-2.0, Python 3.11+)  
**Primary sources:** [docs.activegraph.ai](https://docs.activegraph.ai/), [CONTRACT.md](https://github.com/yoheinakajima/activegraph/blob/main/CONTRACT.md), [README](https://github.com/yoheinakajima/activegraph/blob/main/README.md), [CHANGELOG](https://github.com/yoheinakajima/activegraph/blob/main/CHANGELOG.md), public package surface `activegraph/__init__.py`, `activegraph/runtime/authority.py`, sandbox docs.

## Question

Which stable public ActiveGraph contracts should the product build on—packs, typed tools, behaviors, policies, action authority, event stores, replay, sinks, and runtime APIs—and which documented limitations materially constrain a Windows RPA runtime?

## Executive answer

Build **on** ActiveGraph as the event-sourced lifecycle runtime: append-only log as source of truth, graph as projection, reactive behaviors, pack-delivered domain surface, typed tools for external I/O, policies + action-class authority for gates, SQLite event store per workspace run, fork/replay/promote for repair, and `EventSink` for filesystem evidence export.

Do **not** expect ActiveGraph to provide: multi-threaded action fan-out, a security sandbox for untrusted packs, Windows Credential Manager, Task Scheduler, business-action verification beyond what pack tools/behaviors implement, a dashboard, or multi-machine orchestration. Those stay in the rpa-harness product layer (or OS integration) around the runtime.

---

## 1. Stable contracts to build on

### 1.1 Core runtime model (locked)

| Primitive | Contract to depend on |
| --- | --- |
| **Event log** | Sole source of truth. Mutations are events first; graph is a projection. Events are append-only; corrections emit new events. |
| **Graph** | Objects + typed relations. Developer-owned type strings (no central ontology). Optional Pydantic validation when a pack registers types. |
| **Behaviors** | Reactive unit: `@behavior` / `@llm_behavior` / `@relation_behavior`. Signature `(event, graph, ctx)` (LLM +1 output arg). Failures become `behavior.failed` events; loop continues. |
| **Patches** | Optimistic concurrency via `expected_version`; `patch.proposed` → `applied` \| `rejected`. |
| **Views / frames** | Scoped reads and bounded run context (goal, constraints, budget, registered behaviors). |
| **Queue** | Single in-process FIFO; single-threaded; multi-match behaviors run in registration order. |
| **Determinism** | Behaviors must not use wall clock / random / ambient I/O; use `ctx` / recorded tool+LLM paths so replay and fork stay meaningful. |

**Fixed framework event vocabulary (verbs):** lifecycle (`goal.created`, `runtime.idle`, `runtime.budget_exhausted`), graph mutations, behavior lifecycle, patterns, `llm.*`, `tool.*`, patches, approvals, packs (`pack.loaded` / `pack.disabled`), plus later `authority.*`, `embedding.*`, `dev.override`, optional `context.read`. Custom application event type strings are allowed.

**Product implication:** RPA lifecycle state (intent → approval → action → verification → evidence → repair → completion) should be modeled as **graph objects/relations + events**, not as a parallel orchestration database.

### 1.2 Packs (primary product packaging unit)

Packs are the stable extension unit for a domain product.

- A pack is a **Python package** exporting a frozen `Pack(name, version, …)` — not a YAML/JSON-only manifest.
- Bundles: object types, relation types, behaviors, tools, prompts (markdown + TOML frontmatter), policies, optional `settings_schema`, optional fixtures.
- Discovery: Python entry point group `activegraph.packs`.
- Load API: `Runtime.load_pack(pack, settings=…)`; idempotent on `(name, version)`; conflict detection **before** any mutation (`PackConflictError` / `PackVersionConflictError`).
- Namespacing: behaviors/tools/policies register as `{pack}.{short_name}`; short-name lookup is lenient when unambiguous.
- Pack-aware decorators import from `activegraph.packs` (must not pollute global registries on import).
- Manifest/surface validation: `load_manifest` / `verify_surface`, content + bundle hashes (v1.4+); capabilities may declare `action_class` (v1.9).
- `disable_pack(name)` deregisters live surface without rewriting history.
- **Trust model (locked):** packs are **not sandboxed**. Installing a pack is installing arbitrary Python. Trust at install time.

**Product implication:** ship rpa-harness as one or more first-party packs (e.g. workspace automation, browser tools, desktop tools, evidence sinks) rather than as a “bridge” beside ActiveGraph.

### 1.3 Typed tools (external I/O boundary)

| Rule | Detail |
| --- | --- |
| Registration | `@tool(name, description, input_schema, output_schema, cost_per_call, timeout_seconds, deterministic=…)` |
| Invocation | Event pair `tool.requested` / `tool.responded`; args + outputs schema-validated. |
| Context | `ToolContext` has **no graph**. Tools must not mutate graph; return data for the calling behavior to record. |
| Replay | **All tools serve from cache by default** on replay; opt-in re-invoke only for marked deterministic tools via `replay_reinvoke_deterministic`. |
| Failures | Structured `ToolError` reasons (`tool.timeout`, `tool.network_error`, `tool.execution_error`, …) mapped into `tool.responded.error` and often `behavior.failed`. |
| External I/O honesty | Direct body call of reference `web_fetch` outside the runtime loop fails closed unless `live_unrecorded` is explicit (v1.8). |
| Idempotency | `ToolContext.idempotency_key` is an opaque pass-through for external APIs; runtime does **not** use it for automatic dedupe. |

**Product implication:** Playwright clicks, UIA actions, Excel writes, and credential vault operations must be **`@tool` implementations** (or thin factories closed over drivers), never raw I/O inside `@behavior` bodies. Verification outcomes should land as graph mutations / custom events after tool results return.

### 1.4 Policies and approvals

- Pack policies (`PackPolicy`) gate selected object types (and related proposal paths).
- Operator path: `approval.proposed` → `runtime.approve` / `runtime.deny` → `approval.granted` / `approval.denied`.
- Behaviors use `ctx.propose_object(...)` for gated creates; denials are events, not exceptions.
- Settings keys can auto-approve in non-prod.

**Product implication:** workflow-version and side-effect scope approvals should map onto ActiveGraph approval + (v1.9) action-class evaluation, not a separate ad-hoc gate stack that reimplements the same lifecycle.

### 1.5 Action-class authority (v1.9 — canonical)

Closed **action classes:** `R0 | R1 | R2 | R3 | R4`  
Closed **automatic ceilings:** `none | R0 | R1 | R2` (R3/R4 can never be automatic ceilings)

Fixed evaluation order (`evaluate_action_authority` / `Runtime.evaluate_capability_authority`):

1. Missing/invalid `action_class` → **require_approval** (fail closed)
2. `R4` → **governance_gate** always
3. `R3` → **require_approval** always
4. `R0`–`R2` → **auto_approve** only if ≤ effective ceiling (stricter of instance ceiling and optional per-capability ceiling)

Every evaluation emits an auditable `authority.decision` event. Ceiling changes are log facts (`authority.ceiling_changed`). No mapping exists between legacy `risk_class` and `action_class`.

**Product implication:** declare RPA capabilities with `action_class` on pack surfaces. Map business side effects (browser submit, desktop commit, credential use) to R-classes and set workspace ceilings so healthy approved workflows can run unattended only up to an explicit automatic ceiling.

### 1.6 Event stores and graph stores

| Seam | Contract |
| --- | --- |
| **EventStore** | Protocol: `append`, `iter_events`, `get_event`, `count`, `truncate_after`, `close`. Implementations: `InMemoryEventStore`, `SQLiteEventStore` (default), `PostgresEventStore` (extra). |
| Addressing | URL form: `sqlite:///…`, `sqlite:////abs…`, `postgres://…`. Bare paths rejected on CLI/library open helpers (except legacy `Runtime.load` sugar). |
| Schema | `events`, `runs`, `meta`; `UNIQUE(id, run_id)`; `meta.schema_version` hard-checked. |
| **GraphStore** | Pluggable projection; default in-memory; `FalkorDBGraphStore` is the first external backend. |

**Product implication for Windows workspace install:** default to **per-workspace SQLite** event DB under the workspace data root. Postgres is optional later for multi-inspector setups; not required for local-first RPA.

### 1.7 Replay, fork, promote, compaction

| Capability | What to rely on |
| --- | --- |
| **Load / resume** | Rebuild projection from log; re-queue unfired events (not in-flight partial work). |
| **Strict replay** | Re-fire behaviors; fail on divergence (`ReplayDivergenceError`). LLM/tool/embedding caches make forks cheap. |
| **Fork / diff** | Branch at any event; structural diff vs parent; cache replay of shared prefix. |
| **Promote** | Apply fork’s net structural delta to parent; fail-closed on conflicts (fork→test→promote loop). |
| **Trials** | `run_forked_trial` / `TrialExecutor`: subprocess isolation for candidate pack changes; **crash isolation, not security sandbox**. |
| **Compaction (v1.5)** | Snapshot + archive tier + retention pins; **never silent deletion**. |
| **run_quantum (v1.10)** | Cooperative single-writer drains for hosts that must interleave reads/commands; no false `runtime.idle` on yield. |

**Product implication:** selector/workflow repair should prefer **fork → trial → promote** (or evidence-backed patch objects) over mutating live history. Unattended low-risk repairs still need recorded authority + validation.

### 1.8 Event sinks (observation / evidence export)

- `EventSink` protocol: `open` / `on_event` / `flush` / `close`.
- Offered **only after** accept into log + projection (+ durable store).
- Bounded per-sink queue + daemon worker; overflow policies explicit; loss visible in `SinkStatus` + metrics.
- First-party `JSONLEventSink`; `RecordingSink` for tests.
- **Normal load/fork/strict replay never redeliver history** to live sinks. Historical export is a separate future mode.

**Product implication:** map rpa-harness `timeline.jsonl` / evidence streaming to sinks (or a thin product adapter that also writes screenshots/DOM/UIA artifacts referenced by graph objects). Do not dual-write a second “source of truth” event log.

### 1.9 Runtime / CLI / observability public APIs

Stable product host surface includes:

- `Runtime`, `Graph`, `Frame`, `Budget`, `Policy`, pack load/disable, `run_goal` / `run_until_idle` / `run_quantum`
- Approvals: `pending_approvals`, `approve`, `deny`
- Authority: `authority_ceiling`, `set_authority_ceiling`, `evaluate_capability_authority`
- Persistence: `save_state`, `Runtime.load`, `fork`, `diff`, `promote`
- Operator: `status()`, structured logging schema, `Metrics` protocol (Prometheus/OTel optional)
- CLI: `quickstart`, `inspect`, `replay`, `fork`, `diff`, `export-trace`, `migrate`, `pack list|new`
- Explicit local bypass: `dev_override` receipts (no global dev mode; cannot grant R4 or override promotion/logging)

---

## 2. Documented limitations that constrain Windows RPA

These are material for product design—not just footnotes.

### 2.1 Concurrency and process model

- Runtime is **single-threaded, single-writer**. No async behavior fan-out, no distributed orchestrator.
- Product map constraint “one write-capable run per workspace” aligns with ActiveGraph; concurrent **read-only** inspection should use separate load/replay or sink consumers, not concurrent writers on one run.
- Use `run_quantum` when the host (CLI/MCP server) must stay responsive.

### 2.2 Side effects and replay

- Tool results are **cached by default on replay**. Replaying a run will **not** re-click the browser or re-type into a desktop app unless intentionally re-invoking deterministic tools.
- Therefore: **execution** of non-idempotent business writes must be gated so recovery/resume never assumes “re-run the log = re-do the write.” Success must be proven and recorded **after** the tool returns (product verification contract), and non-idempotent tools must remain non-deterministic / non-auto-reinvoke.
- Direct I/O inside behaviors breaks the replay contract and is forbidden by the determinism rules.

### 2.3 Trust and isolation

- Packs = trusted code. Do not load third-party packs as a security boundary for business systems.
- Local trial executor: **shared filesystem, unconfined network/syscalls**; memory `RLIMIT_AS` **announced-unavailable on Windows** (and macOS). Rely on wall-clock kill + event budgets, plus product-level policy, not OS rlimits.
- `dev.override` is audited but is not a substitute for production approval of R3/R4.

### 2.4 What ActiveGraph does not ship (product must own)

| Gap | Product ownership |
| --- | --- |
| Windows Credential Manager / secret redaction pipeline | rpa-harness security edge; tools receive secret *names* or vault handles, never log plaintext |
| Windows Task Scheduler / unattended triggers | Product installer + scheduler registration; AG is the run engine once started |
| Browser/desktop drivers, selector strategy, screenshots, UIA dumps | Product tools + evidence adapters |
| Explicit success verification beyond tool return | Product behaviors/checks after tool results (AG only records what you emit) |
| MCP server / human CLI product UX | Product application services wrapping AG Runtime |
| Multi-machine / hosted control plane | Explicitly out of AG and out of this Wayfinder map |
| Built-in dashboard / HTTP server | Optional; use sinks + local files |
| Wall-clock `activate_after` | Event-count only; timers require external host ticks if needed |
| Historical sink redelivery | Export via CLI/`export-trace` or future replay_export; don’t invent dual logs |
| YAML as pack format | AG is Python-pack + TOML prompt frontmatter; YAML stays **migration/import only** for rpa-harness |

### 2.5 Operational limits

- In-flight behavior loss on crash is accepted (work after last emitted event is lost).
- Compaction does not freely delete; retention pins matter for evidence longevity.
- Event volume for a full RPA journey (screenshot metadata, DOM snippets) may be large; map issue already flags retention/compaction as **not yet specified** until a representative run exists.
- Operator logging can include prompts/payloads; product redaction must wrap logging **and** any evidence files (AG log redactor does not rewrite the event store).

### 2.6 Upstream contribution vs local extension vs avoid

| Concern | Recommendation |
| --- | --- |
| Pack of RPA object types/behaviors/tools | **Local / first-party pack** on public pack API |
| Browser/desktop tools, verification behaviors | **Local** tools + behaviors |
| Credential vault tool | **Local** tool; do not expect upstream secrets pack to replace WCM policy |
| JSONL + screenshot path coupling | **Local EventSink** or product writer triggered by sink/behavior |
| Stronger Windows trial resource limits | **Avoid blocking** on upstream; use host process isolation if needed; optional upstream contribution later |
| Making non-idempotent external writes “safe under default replay re-invoke” | **Avoid** fighting cache-by-default; design verification + authority instead |
| Parallel multi-writer runtime | **Avoid**; product concurrency policy instead |

---

## 3. Recommended build surface for rpa-harness (summary)

**Build on (public, stable enough for a transformation design):**

1. `Pack` + entry-point discovery + settings + `pack.loaded` audit  
2. `@behavior` / `@relation_behavior` / optional `@llm_behavior` for orchestration & repair reasoning  
3. `@tool` for every external side effect (browser, desktop, Excel, vault, network)  
4. `PackPolicy` + `approve`/`deny` + **v1.9 `action_class` / authority ceiling**  
5. SQLite `EventStore` per workspace; `Runtime.load` / `fork` / `diff` / `promote` / trials  
6. `EventSink` (`JSONLEventSink` + product sinks) for live evidence export  
7. CLI + `Runtime.status` + structured logs/metrics for operator/CI  
8. `run_quantum` for MCP/CLI hosts that interleave commands with drains  

**Do not build on / do not assume:**

- Multi-threaded AG execution, distributed runtime, or security-sandboxed packs  
- Automatic re-execution of business UI actions under replay  
- Upstream Windows Task Scheduler / WCM / Playwright integration  
- YAML as the long-term canonical automation definition  

---

## 4. Open items handed to later Wayfinder tickets

| Deferred question | Owner ticket |
| --- | --- |
| Ownership split AG vs product for evidence files, approvals, credentials | #5 |
| Domain objects/events for automation lifecycle | #6 |
| Deterministic verify + no double-write recovery | #7 |
| Credential + authority coherence | #8 |
| CLI/MCP shared application services | #9 |
| Workspace install + Task Scheduler | #10 |
| YAML import/compat lifetime | #11 |
| Vertical prototype to pressure-test missing extension contracts | #12 |
| Event retention after realistic volume | Map #2 “not yet specified” |

---

## 5. Source index

- Docs home / concept index: https://docs.activegraph.ai/ and https://docs.activegraph.ai/llms.txt  
- Pack authoring: https://docs.activegraph.ai/guides/authoring-packs/  
- Policies: https://docs.activegraph.ai/concepts/policies/  
- Behaviors + determinism: https://docs.activegraph.ai/concepts/behaviors/  
- Production ops (stores, sinks, metrics, CLI): https://docs.activegraph.ai/guides/operating-in-production/  
- Sandbox honesty (Windows RLIMIT): https://docs.activegraph.ai/reference/api/sandbox/  
- CONTRACT / CHANGELOG / public `__init__.py` / `runtime/authority.py` on https://github.com/yoheinakajima/activegraph  

## Decision pointer (for map #2)

> ActiveGraph v1.10 public surface is sufficient as the lifecycle runtime: product extension is pack + typed tools + policies/action_class + SQLite runs + sinks/fork-promote. Material constraints: single-writer runtime, pack trust model, tool cache-on-replay for external I/O, no WCM/scheduler/driver primitives upstream, Windows trial memory limits unavailable.
