# Files, CSV, and JSON

Use typed observations for reads and an Action Boundary for atomic replacement.
Validate the schema before accepting input, write to a temporary sibling, fsync
when the platform supports it, replace atomically, then independently verify
the saved value and attach redacted Evidence.
