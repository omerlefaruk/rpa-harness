---
name: playwright-automation
description: Browser discovery guidance for ActiveGraph browser capability ports.
---

# Browser discovery

Recon-only guidance. Execution uses typed browser ops (`navigate`, `inspect`,
`extract`, `fill`, `click`, `wait`, `download`, `screenshot`) via
`CapabilityExecutor` and the application seam.

Scripts under `scripts/` may help capture discovery evidence. They are not
lifecycle authority and must not be exposed as MCP tools.

Canonical authoring: `rpa-harness-automation-builder`.
