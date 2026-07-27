# ADR-0001: YAML runtime retired

## Status

Accepted — 2026-07-27

## Context

The product historically ran deterministic YAML workflows via a dedicated runner, DSL compile path, and copilot/autopilot builder loops. Those surfaces duplicated lifecycle state in run folders and agent sessions, drifted from EventStore semantics, and conflicted with the ActiveGraph-native goal: one application seam, one lifecycle authority, allowlisted agent tools.

## Decision

YAML is **not** a production runtime. The YAML runner, DSL, copilot, and autopilot modules and CLI flags are removed. Production authoring and execution use `AutomationApplication` + EventStore only. Remaining YAML schema/spec docs are archive banners for import/reference, not operator paths.

## Consequences

- CLI exposes only `--automation-*` flags.
- Agents draft proposal JSON and call MCP/CLI application ops.
- Contract tests lock absence of legacy modules and YAML CLI flags.
- Historical docs under `docs/workflow_spec.md` and `docs/yaml_*.md` stay marked retired.
