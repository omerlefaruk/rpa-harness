# YAML Legacy Migration

Legacy flat workflows still load through the runner, but new workflows should use the default phase-based schema.

Migrate a legacy workflow:

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
