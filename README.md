# rpa-harness

Deterministic, **ActiveGraph-native** RPA automation with evidence.

The AI never gets shell, raw Playwright/UIA drivers, or a YAML runner.  
It calls allowlisted MCP/CLI operations that all go through `harness.automation.AutomationApplication`. The ActiveGraph EventStore (`data/automation-events.sqlite` per workspace) is the sole lifecycle authority; filesystem outputs are projections and exports.

**Core rule:** action execution is not success. Runs complete only after explicit verification (and approval for R3/R4 writes).

## Install as an AI-agent workspace product

```bash
npx rpa-harness-agent init my-workspace
npx rpa-harness-agent mcp
# alias also supported:
npx roi-harness init my-workspace
```

The npm package under `packages/rpa-harness-agent/` is a thin launcher. The runtime is Python; agents connect over MCP with allowlisted tools only.

## Agent loop

1. **Init / status** — pinned workspace runtime  
2. **Draft proposal JSON** — Intent + DiscoveryEvidence + Definition  
3. **`validate` → `register`** — immutable Definition Version  
4. **`grant_approval`** — required for R3/R4 writes  
5. **`execute_read` / `execute_write`** — capability port + verification  
6. **`inspect` / `export_evidence`**  
7. Ambiguous write → **`reconcile`**  
8. Selector failure → **`propose_repair` → `trial_repair` → `promote_repair`**

## CLI (ActiveGraph only)

```bash
python main.py --automation-list-operations
python main.py --automation-init-workspace .rpa-automation
python main.py --automation-workspace-status --automation-workspace .rpa-automation
python main.py --automation-validate-proposal proposals/example.json
python main.py --automation-register-proposal proposals/example.json --automation-workspace .rpa-automation
python main.py --automation-grant-approval grant.json --automation-workspace .rpa-automation
python main.py --automation-execute-read request.json --automation-workspace .rpa-automation
python main.py --automation-execute-write request.json --automation-workspace .rpa-automation
python main.py --automation-inspect RUN_ID --automation-workspace .rpa-automation
python main.py --automation-export-evidence RUN_ID --automation-workspace .rpa-automation
python main.py --automation-reconcile request.json --automation-workspace .rpa-automation
python main.py --automation-propose-repair request.json --automation-workspace .rpa-automation
python main.py --automation-trial-repair request.json --automation-workspace .rpa-automation
python main.py --automation-promote-repair request.json --automation-workspace .rpa-automation
```

Equivalent: `python -m harness.cli --automation-...`.

## Where ActiveGraph sits

```text
You / AI
  → MCP tools (packages/rpa-harness-agent)
    → harness.cli --automation-* flags
      → AutomationApplication
        → ActiveGraph EventStore   ← sole lifecycle authority
      → capability ports (ToolResult only)
        → drivers as adapters
```

YAML runtime, DSL, copilot, and autopilot entrypoints are **retired**. Historical YAML schema notes remain under `docs/` for archive/import context only.

## Canonical agent skill

`.agents/skills/rpa-harness-automation-builder` — Intent → Discovery → Proposal → Validation → Approval → Execution → Verification → Reconciliation → Repair → Promotion.

## Selectors (executable priority)

Browser: `role → label → test_id → css → xpath → coordinate`  
Desktop: `automation_id → name → class → tree_path → image → coordinate`

## OKF knowledge bundle

Repo knowledge is published as an OKF v0.1 bundle under `docs/okf`:

```bash
python scripts/okf.py validate docs/okf
python scripts/okf.py generate-indexes docs/okf
git config core.hooksPath .githooks
```

## Safety

- Secret **names** only in proposals, definitions, logs, and reports; values resolve at the execution edge.
- Non-idempotent external writes are not auto-retried.
- Weak selectors require verification (and approval when policy demands).
- Skills are playbooks; code enforces safety. See `docs/research/code-vs-skill-boundary.md`.

## Docs map

| Doc | Purpose |
| --- | --- |
| `CONTEXT.md` | Domain glossary |
| `docs/adr/` | Architecture decisions |
| `docs/architecture.md` | ActiveGraph layers |
| `docs/operator_workflow.md` | Operator lifecycle |
| `docs/verification_contract.md` | Success checks |
| `docs/credential_policy.md` | Secrets |
| `docs/evidence_and_repair.md` | Evidence + repair |
| `AGENTS.md` | Thin agent non-negotiables |
