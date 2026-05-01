# Credential Rules

## Core Rule

Use secret names only. Never paste real credentials into prompts, code, workflows, logs, screenshots, memory, or tests.

## Sources

Environment variables, `.env` (never committed), OS credential manager, external password manager CLI, CI secret store.

## Redaction

Before writing logs or reports, redact passwords, tokens, cookies, authorization headers, session ids, personal identifiers.

## Screenshot Safety

Store in local run folders. Do not upload automatically. Do not summarize sensitive content into memory. Redact if necessary.

## See Also

`docs/credential_policy.md` — full policy
