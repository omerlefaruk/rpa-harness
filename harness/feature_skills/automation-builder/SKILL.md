# Automation Builder

Build an ordinary Python automation in this order: state the intent, perform
read-only discovery, scaffold a source snapshot, validate its Action Manifest,
register the immutable revision, execute through a Workflow Context, inspect
the graph-backed run, and export accepted Evidence.

The application interface owns authority, budgets, replay, and verification.
This document is guidance and is not parsed as policy.

## Runnable example

See `examples/r0_read.py`. It defines `main(payload)` and returns JSON data.
