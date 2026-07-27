# Credential Rules

Use secret **names** only in proposals, definitions, logs, prompts, and reports. Resolve secret values only at the local execution edge.

Canonical policy: `docs/credential_policy.md`.

Never paste real credentials into code, EventStore payloads, evidence exports, repair packets, or tests.
