# rpa-harness-agent

Thin npm launcher for the **ActiveGraph-native** rpa-harness product.

The AI never gets shell, raw Playwright/UIA drivers, or a YAML runner.  
It only calls allowlisted MCP/CLI operations that all go through `AutomationApplication`.

## Quick start

```bash
npx rpa-harness-agent init my-workspace
npx rpa-harness-agent mcp
```

## Agent loop (what the AI does)

1. **Init / status** — pinned workspace runtime  
2. **Draft proposal JSON** — Intent + DiscoveryEvidence + Definition (AI writes the file)  
3. **`validate_automation_proposal`** → fix until accepted  
4. **`register_automation_proposal`** → immutable Definition Version  
5. **`grant_automation_approval`** — required for R3/R4 writes  
6. **`execute_automation_read` / `execute_automation_write`** — capability port + verification  
7. **`inspect_automation_run` / `export_automation_evidence`**  
8. On ambiguous write → **`reconcile_automation_run`**  
9. On selector failure → **`propose_automation_repair` → `trial_automation_repair` → `promote_automation_repair`**

## Where ActiveGraph sits

```text
You / AI
  → MCP tools (this package)
    → harness.cli flags
      → AutomationApplication
        → ActiveGraph EventStore   ← sole lifecycle authority
      → capability ports (ToolResult only)
```

YAML runner used files + ad-hoc retries as truth.  
ActiveGraph records every admit/attempt/verify/block as an event; re-open and inspect always replay the same log.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `list_automation_operations` | Catalog |
| `init_workspace` / `workspace_status` | Runtime pin |
| `propose_automation` | Admit agent-authored proposal |
| `validate_automation_proposal` | Deterministic validation |
| `register_automation_proposal` | Definition Version |
| `grant_automation_approval` | Approval Grant |
| `execute_automation_read` / `execute_automation_write` | Run with capability port |
| `reconcile_automation_run` | Resolve unknown writes |
| `propose/trial/promote_automation_repair` | Fork repair |
| `inspect_automation_run` / `export_automation_evidence` | Projection + evidence |

Not exposed: `shell`, `exec`, `run_python`, raw driver clicks, YAML `run`/`validate`.

## Request shapes (relative paths only)

**Execute write** (`request_path`):

```json
{
  "definition_id": "inventory-write",
  "version": 1,
  "grant_id": "grant_…",
  "actor": "operator@example",
  "port": "fake_browser",
  "op": {
    "name": "fill",
    "action_class": "R3",
    "read_only": false,
    "inputs": { "value": "${secrets.api_token}" },
    "selector": { "strategy": "label", "locator": "Qty", "verified": true }
  },
  "secrets": { "api_token": "edge-only-value" }
}
```

Default `port` values use deterministic fakes (`fake_browser`, `fake_api`, `fake_excel`, `fake_desktop`) so agents can complete loops in CI. Real drivers can share the same `op` schema later without adding MCP escape hatches.
