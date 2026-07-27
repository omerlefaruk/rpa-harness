# ADR-0003: EventStore is lifecycle authority

## Status

Accepted — 2026-07-27

## Context

Filesystem run folders, HTML reports, and ad-hoc session state previously competed as sources of truth. ActiveGraph EventStore can record every admit/attempt/verify/block as an append-only event so re-open and inspect always replay the same log.

## Decision

The **EventStore** (typically `data/automation-events.sqlite` per workspace) is the sole lifecycle authority for automation runs, definition versions, approval grants, verification, reconciliation, and repair. `AutomationApplication` is the only writer of lifecycle events for a write-locked workspace. Inspect and run summaries are projections. Filesystem evidence is an export that follows an Evidence Reference event.

## Consequences

- Drivers and capability ports return `ToolResult` only; they do not append lifecycle events.
- Operators and agents use inspect/export rather than treating reports as primary truth.
- Repair mutates definitions only via fork trial + promote to a new version.
- Workspace locks prevent concurrent writers from forking the log.
