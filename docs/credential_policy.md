# Credential Policy

## Rule

Credentials must never be pasted into prompts, source code, workflows, reports, logs, screenshots, memory, or tests.

Use secret names only.

## Allowed Format

```yaml
credentials:
  profile: simphony_prod
  username_secret: SIMPHONY_USERNAME
  password_secret: SIMPHONY_PASSWORD
```

## Disallowed Format

```yaml
username: real-user@example.com
password: real-password
```

## Secret Sources

Allowed:
- environment variables
- `.env` local file, never committed
- OS credential manager
- external password manager CLI
- CI secret store

## Redaction Rules

Before writing logs or reports, redact:
- passwords
- tokens
- cookies
- authorization headers
- session ids
- personal identifiers where unnecessary

## Screenshot Safety

Screenshots may contain sensitive data.
- Store in local run folders only
- Do not upload automatically
- Do not summarize sensitive content into long-term memory
