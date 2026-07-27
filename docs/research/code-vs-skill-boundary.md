# Code vs skill boundary inventory

**Wayfinder context:** map [#2](https://github.com/omerlefaruk/rpa-harness/issues/2) (ActiveGraph-native product) + skills-surface workstream  
**Researched:** 2026-07-27  
**Depends on:** [activegraph-extension-boundaries.md](./activegraph-extension-boundaries.md), [activegraph-retention-inventory.md](./activegraph-retention-inventory.md)

## Question

What must stay in executable code, and what can become (or stay as) agent `SKILL.md` / rules / docs—without losing enforcement or inventing a second runtime?

## Executive decision

| Layer | Owns |
| --- | --- |
| **Code (enforcement)** | Validation, drivers/tools I/O, verification after action, redaction, artifact writers, allowlists, repair apply gates, retry safety, failure classification used by the runner |
| **Config (machine policy)** | `.agents/config/autopilot.yaml`, `agent_command_manifest.json` — loaded and enforced by code, not skills |
| **Docs (human contracts)** | verification, credentials, selectors, evidence/repair, mutation, workflow_spec — single prose canon per topic |
| **Rules (thin agent constraints)** | `.agents/rules/*` — short non-negotiables + **pointers** to docs; no full catalog copies |
| **Skills (agent playbooks)** | How to author, inspect, discover, draft, preflight, repair, and use CLI/MCP—**procedure only** |
| **OKF** | Indexed mirrors of durable system knowledge; not a third independent policy |

**Hard rule:** A skill may *summarize* a contract. It must never be the only place a safety rule exists. When prose and code disagree, **code wins** until docs/skills are fixed.

**AG rule:** Re-hosting under ActiveGraph does not move enforcement into skills. Verification, redaction, tools, and authority remain executable (pack tools, policies, `action_class`, sinks).

---

## 1. Must stay in code (never skill-only)

| Domain | Primary code | Why |
| --- | --- | --- |
| Secret resolve + redaction | `harness/security.py`, artifact writers, runner secret edge | Leak prevention |
| Success-check schema + execution | `verification/contract.py`, `checks.py` | Action ≠ success is enforced |
| Drivers / external I/O | `drivers/*`, `rpa/excel.py`, desktop clipboard/OCR | Real side effects |
| Workflow schema / migrate / preflight | `rpa/schema.py`, validation paths | Invalid workflows rejected |
| Runner execute path (until AG rehost) | `rpa/yaml_runner.py`, `execution_plan.py`, `ledger.py` | Deterministic lifecycle today |
| Rulebook scoring / side-effect / retry safety | `core/rulebook.py` | Production readiness is scored in code |
| Failure classification used by runner | `resilience/errors.py` | Routes must match reports |
| Retry/recovery helpers | `resilience/recovery.py` | Non-idempotent writes must not be soft-retried |
| Reporting / evidence packaging | `reporting/*` | Redacted artifact contracts |
| Selector scoring, swarm, production patch | `selectors/*` | Apply path needs validated candidate + approve |
| MCP allowlist + path sandbox | `packages/rpa-harness-agent/lib/*` | No shell; relative paths only |
| Autopilot policy gates | `autopilot.py` + `autopilot.yaml` | External write / submit / coordinate |
| AI tool default-deny | `ai/tools.py` | Unapproved tools fail closed |
| Runtime LLM I/O contracts | `ai/agent.py`, `planner.py`, `vision.py` prompts | Live behavior; keep in code (align content) |
| Product init tree copy | `product_init.py` | Installer behavior |
| Skill helper scripts | `.agents/skills/*/scripts/*` | Executables, not prose |

### Never put *only* in a skill

1. Required success checks / ban of abusive `always_pass`  
2. Secret redaction and secret-name-only workflows  
3. Driver clicks, API writes, Excel mutations  
4. Autopilot allow_* gates  
5. Production selector patch without validation + approve  
6. MCP tool expansion / shell access  
7. Unsafe automatic retry of non-idempotent writes  
8. Mutation-protocol bypass for protected core  
9. “Production ready” without rulebook/audit code  
10. Parallel free-form agent loop as a substitute for approved workflows  

---

## 2. Stay as skills / extract to skills (procedure only)

### Existing skills — disposition

| Skill | Disposition | Notes |
| --- | --- | --- |
| `.agents/skills/rpa-harness-automation-builder` | **CANONICAL builder skill** | Full author/inspect/repair loop |
| `skills/rpa_harness_automation_builder` | **DELETE or thin redirect** after merge | Near-duplicate; OKF may cite it—update citations |
| `search-to-rpa-workflow` | **MERGE** intake phase into builder *or* keep as short intake-only skill | Large overlap with builder |
| `playwright-automation` | **KEEP** | Recon-then-action + scripts; drop divergent selector ladder (link `docs/selector_strategy.md`) |
| `windows-ui-automation` | **KEEP** | Discover→act + scripts; link legacy desktop strategy for weak UIA |
| `excel-workflows` | **KEEP** | Domain YAML patterns; expand multi-row ledger later |
| `selector-strategies` | **ALIGN or fold** into selector_strategy.md + one skill | Ladder currently diverges from AGENTS/code |
| `error-recovery` | **REWRITE** against code taxonomy | Must not invent parallel RETRY/SKIP/FALLBACK enums that disagree with `classify_failure` / rulebook routes |
| Root `SKILL.md` | **KEEP thin** product card | Point to builder + README; no second architecture |

### New / missing skill candidates (extract from docs/code prose)

| Candidate skill | Extract from | Code remains |
| --- | --- | --- |
| `evidence-and-repair` | `docs/evidence_and_repair.md`, failure_report fields, operator failure path | Artifact writers, repair apply |
| `rulebook-readiness` | `core/rulebook.py` field meanings, audit CLI | `audit_workflow_rulebook` |
| `failure-to-repair-map` | `classify_failure`, repair_packet, CLI repair/retry | Classification functions |
| `selector-swarm-and-approve` | swarm CLI, `production_selector_repair`, approve gate | Swarm + patch code |
| `desktop-ai-assist` | `desktop/ai_controller.py` modes | Controller I/O and gates |
| `credential-hygiene-authors` | credential_policy (thin skill) | `security.py` |
| `mcp-operator-surface` | MCP tool list, no-shell rule | Allowlist implementation |
| `okf-maintenance` | OKF docs + commands (one place) | `scripts/okf.py` |
| optional `dsl-authoring` | README DSL section | `dsl.py` compiler |

### Rules — disposition

| Rule | Disposition |
| --- | --- |
| `00-role`, `01-core`, `05-enforcement`, `04-hooks`, `07-telegram-voice` | **KEEP** (thin process) |
| `03-verification`, `06-credentials`, `04-mutation-protocol` | **SHRINK to pointers** → docs are canonical |

### Config — not skills

| Path | Disposition |
| --- | --- |
| `.agents/config/autopilot.yaml` | **STAY machine policy** enforced by code |
| `.agents/config/agent_command_manifest.json` | **STAY allowlist** enforced by agent/MCP paths |

---

## 3. Split modules (code keeps enforcement; skill owns playbook)

| Module | Code keeps | Skill / doc owns |
| --- | --- | --- |
| `selectors/strategies.py` + swarm + repair | Scoring, validation, patch/approve | Priority ladder narrative, when to swarm, how to read candidates |
| `core/rulebook.py` | Audit score, side-effect/retry safety | How to fill rulebook fields for unattended readiness |
| `autopilot.py` / copilot* / builder | Session state, policy gates, artifacts | Phase loop, when to pause, how to answer gates |
| `ai/*` | Tool registry, prompts as runtime, history | Optional planning playbook; do not dual-orchestrate production |
| `cli.py` | Flag dispatch | Command recipes in builder/operator skills |
| `dsl.py` | Compile to YAML | When/how to write `.rpa` |
| `reporting/*` | Emit redacted packets | How agents consume evidence |

---

## 4. Duplication clusters to fix (skills track)

1. **Builder skill doubled** — `.agents/skills/...` vs `skills/`  
2. **Browser selector ladder** — AGENTS, docs, 3 skills, `planner.py` prompt, `strategies.py` (code is scoring truth)  
3. **Desktop ladder** — AGENTS, docs, skills, desktop AI strings; deep form in `legacy_desktop_strategy.md`  
4. **Evidence list** — AGENTS, builder skills, evidence doc, OKF, README  
5. **Verification check catalog** — rule 03 ≈ verification_contract (doc wins; code enums win for enforcement)  
6. **Error taxonomies disagree** — error-recovery skill vs rulebook routes vs `analyze_failure` vs failure_report  
7. **Credentials / mutation** — full text in rules + docs; rules should point  
8. **OKF maintenance** — repeated in AGENTS + both builder skills  

---

## 5. Ownership model (single home per concern)

```text
Enforcement          → harness/ code + .agents/config/*
Human contract       → docs/<topic>.md
Agent non-negotiable → .agents/rules/* (short) + AGENTS.md (thin root)
Agent playbook       → .agents/skills/<name>/SKILL.md  (+ scripts if needed)
System index         → docs/okf/* (mirrors; regenerate indexes)
Product card         → root SKILL.md + README.md
```

**Canonical skill root:** `.agents/skills/` (agent home).  
**Deprecate:** parallel long-form skill under `skills/` once redirects/OKF updated.

---

## 6. Relationship to ActiveGraph Wayfinder

| Track | Scope |
| --- | --- |
| **AG map (#2)** | Lifecycle SoT, packs/tools, authority, YAML import, CLI/MCP services, WCM, Task Scheduler |
| **Skills workstream** | Agent knowledge surface: dedupe, align, extract playbooks—**no runtime replacement** |
| **Shared freeze** | Do not skill-ify modules scheduled for AG rehost as if skills were the migration; when rehosting, re-port **enforcement** to AG tools/policies, update skills to teach the new surfaces |

Skills work may run **in parallel** on markdown/rules only. Touching protected harness core for “move guidance out of strings” needs mutation protocol + tests; prefer extracting *copies* into skills and leaving short runtime strings unless a shared constant is introduced deliberately.

---

## 7. Suggested workstream tickets (for map update)

1. **Decide skill surface ownership** (grill or accept this doc): canonical roots, rules-as-pointers, config stays code.  
2. **Consolidate skills:** merge dual builder skills; align/fold selector-strategies; rewrite error-recovery against code taxonomy; fix OKF citations.  
3. **Extract missing playbooks:** evidence-and-repair, rulebook-readiness, failure-to-repair, swarm+approve, desktop-ai-assist, thin MCP skill.  
4. **Align embedded prompts:** planner/agent/vision selector and safety strings match `docs/selector_strategy.md` + verification contract (shared constant optional).  
5. **Thin rules + AGENTS:** remove full duplicated catalogs; link docs; keep non-negotiables.  

Out of scope for skills track: implementing AG runtime, changing verification semantics, expanding MCP to shell, deleting drivers.

---

## 8. Decision pointer (for map #2)

> **Code vs skill (2026-07-27):** Enforcement stays code (verification, redaction, drivers, schema, repair apply, allowlists, autopilot gates, classification). Skills own agent procedures only. Canonical skill home: `.agents/skills/`. Merge duplicate builder skill; align selector/error taxonomies with code; extract missing repair/swarm/desktop-AI/rulebook playbooks; shrink rules to pointers at docs. Full inventory: `docs/research/code-vs-skill-boundary.md`.
