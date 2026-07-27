# YAML Legacy Migration

> **RETIRED AS PRODUCTION RUNTIME (2026-07-27).** The YAML runner and `--migrate-workflow` CLI path are removed from the product surface. This document is historical archive only. Migrate business intent into ActiveGraph Automation Proposals instead of phase YAML. See `docs/adr/ADR-0001-yaml-runtime-retired.md` and `.agents/skills/rpa-harness-automation-builder`.

~~Historical note:~~ legacy flat workflows once migrated to phase-based schema via:

Migrate a legacy workflow (historical command — no longer in CLI):

```bash
python main.py --migrate-workflow workflows/examples/minimal_example.yaml --workflow-output workflows/examples/minimal_example.schema.yaml --migration-report migration_report.md
```

The migration preserves:

- workflow id, name, and description
- inputs and declared credentials
- steps and phase fields
- actions and selectors
- existing success checks

The migration does not invent business logic or fake success checks. Unclear fields are reported in the migration report for manual review.
