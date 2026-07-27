---
type: Runtime
title: ActiveGraph automation
description: Event-sourced R0 automation with governed proposal registration, verified completion, and evidence references.
tags: [rpa-harness, activegraph, runtime, evidence]
timestamp: 2026-07-27T00:00:00Z
---

# Behavior

`harness.automation.AutomationApplication` is the shared application interface for the initial ActiveGraph-native path. It accepts versioned typed Automation Intents, Discovery Evidence, Automation Proposals, Definitions, and immutable Definition Versions. Model output is only an Automation Proposal; deterministic validation decides whether it can be registered. The application also executes an injected R0 adapter, records explicit Verification Results, and projects Run summaries only from the ActiveGraph EventStore.

Proposal admission accepts only the `read` capability and `R0` action class. It requires explicit success checks, rejects unresolved business ambiguity, plaintext secrets, unknown capabilities, and unverified CSS, XPath, or coordinate selectors. Secret references may use names only. Proposal and model-call budgets are bounded at the application boundary.

Each workspace uses `data/automation-events.sqlite`. Only one write-capable application instance may hold the workspace lock. Read-only inspectors do not take that lock and rebuild their summaries from the event log.

# Evidence

The application appends an Evidence Reference before writing the referenced JSON evidence export. A Run becomes `completed` only after a passing verification. A failed verification becomes `failed` with a failure kind and Evidence Reference.

# Interfaces

The CLI adapter initializes workspaces with `--automation-init-workspace`, reads projected Run summaries with `--automation-inspect RUN_ID --automation-workspace PATH`, and registers a proposal JSON file with `--automation-register-proposal FILE --automation-workspace PATH`. The MCP bridge exposes only this allowlisted registration operation, never a shell or raw driver.

# Relationships

* Invoked from the [CLI](/interfaces/cli.md).
* Implements the ActiveGraph-native runtime boundary.
