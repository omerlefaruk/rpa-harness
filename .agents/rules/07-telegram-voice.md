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
- Memory save/indexing notes go to `memories`.

## Automatic Hooks

- Ask in `questions` when a workflow cannot start because secrets, config, or action support is missing.
- Post to `failures` when a record, YAML step, or critical agent step reaches a terminal failure.
- Post to `rants` when retries, fallbacks, waits, or recovery actions are needed.
- Post to `memories` when a meaningful workflow or agent summary is saved.
- Do not post for every normal step; only post when the user would actually want to know.

## Safety

- Never include credentials, raw tokens, cookies, or private data.
- Mention secret names only.
- Keep message text concise enough to scan on mobile.
