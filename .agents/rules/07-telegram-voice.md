# Telegram Bot Voice

Bots posting into Telegram topics should sound like coworkers, not system logs.

## Style

- Use short, plain messages.
- Lead with the practical status or decision needed.
- Say what happened, what is blocked, and what the next useful move is.
- For frustration/rant messages, be honest about friction but stay useful.
- Avoid fake personality, jokes, theatrics, blame, and filler.

## Topic Routing

- Reports go to `reports`.
- Questions go to `questions`.
- Failures go to `failures` when the message is mainly about a broken run.
- Rants/friction notes go to `rants`.
- Deploy updates go to `deployments`.

## Automatic Hooks

- Ask in `questions` when an automation cannot start because secrets, config, approval, or capability support is missing.
- Post to `failures` when a run reaches a terminal failure (`failed`, `blocked`, `rejected`).
- Post to `rants` when reconcile, repair trial, or recovery steps are needed.
- Do not post for every normal step; only post when the user would actually want to know.

## Safety

- Never include credentials, raw tokens, cookies, or private data.
- Mention secret names only.
- Keep message text concise enough to scan on mobile.
