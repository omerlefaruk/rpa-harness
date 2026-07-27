---
name: excel-workflows
description: Excel capability guidance for ActiveGraph excel_read/excel_write ports.
---

# Excel automation

Use capability ops `excel_read` / `excel_write` through `CapabilityExecutor` and
`AutomationApplication`. No YAML workbooks runtime.

- Reads are R0; writes are R3 with approval + idempotency scope.
- Row evidence is referenced (path/uri), not embedded in EventStore.
- Credentials stay handle-only when sheets hold secret refs.

Canonical authoring: `rpa-harness-automation-builder`.
