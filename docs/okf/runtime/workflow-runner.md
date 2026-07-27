---
type: Runtime
title: YAML workflow runner (retired)
description: Historical note — YAML runtime is retired; production uses ActiveGraph AutomationApplication.
tags: [rpa-harness, runtime, workflow, retired, historical]
timestamp: 2026-07-27T00:00:00Z
---

# Status

**Retired.** The YAML workflow runner (`harness.rpa.yaml_runner`), DSL, copilot, and autopilot modules are removed from the product surface. Do not document or reintroduce `--run-yaml` / `--validate-yaml` as production paths.

# Historical behavior

The former YAML runner loaded workflow definitions, resolved declared inputs and secrets at the execution edge, ran preflight checks, executed steps, evaluated success checks, and wrote redacted run artifacts under `runs/`. Run folders were treated as the operator source of truth.

# Replacement

Production lifecycle authority is [ActiveGraph automation](/runtime/activegraph-automation.md): EventStore events via `AutomationApplication`, capability ports, approval grants, reconcile, and repair forks. Schema notes in `docs/workflow_spec.md` and `docs/yaml_*.md` are archive banners only.

# Relationships

* Superseded by [ActiveGraph automation](/runtime/activegraph-automation.md).
* Historical CLI entrypoints removed from the [CLI](/interfaces/cli.md) concept.

# Citations

[1] [ADR-0001 YAML runtime retired](../../adr/ADR-0001-yaml-runtime-retired.md)
