# Autonomous Self-Improvement Mode

The harness now has a free-mutation autonomy profile. It can run continuously, scan heartbeat evidence and technology-radar changes, ask the coding agent to patch the repository, benchmark the result, commit the winning diff, merge it into `main`, and push it without waiting for human input.

This is configured by `.autoresearch/autoresearch.sovereign.json` and exposed through:

```bash
python main.py --self-improve-once
python main.py --self-improve-24-7
scripts/self_improve_once.sh
scripts/start_self_improving_daemon.sh
```

The default `.autoresearch/autoresearch.supervisor.json` is also set to the free profile.

## What “free” means

Free mode removes the narrow allowed-path edit boundary. The agent may change repository source, tests, docs, workflows, scripts, configs, CLI surfaces, autoresearch files, and project metadata when a heartbeat candidate justifies it.

Free mode does not mean the process should corrupt the host machine. The supervisor still owns containment:

- code edits happen in an isolated git worktree;
- the agent is told not to commit, merge, push, reset, or touch credentials;
- generated reports, runs, screenshots, downloads, logs, local databases, virtual environments, git internals, and credential files remain blocked;
- a secret scan runs on changed text files;
- the deterministic benchmark and correctness checks must accept the run;
- merge is fast-forward only;
- post-merge checks run on `main`;
- failed post-merge checks trigger rollback to the pre-merge SHA;
- every cycle writes audit JSONL and a compact memory lesson.

The automated review gate is disabled in the free profile because the user requested unattended code mutation. Re-enable it by setting `"require_review": true` in `.autoresearch/autoresearch.sovereign.json`.

## Heartbeat flow

Each cycle performs this sequence:

1. run heartbeat checks;
2. scan TODO/FIXME markers, failure reports, RPA Memory, and technology-radar candidate files;
3. run read-only scout agents;
4. build a repository-scope prompt;
5. create or update the isolated worktree;
6. let the coding agent patch the repo;
7. run the autoresearch benchmark and correctness checks;
8. enforce generated-artifact and secret gates;
9. write a skipped-review report when `require_review=false`;
10. commit, tag, merge, run post-merge checks, and push when configured.

## Installing 24/7 execution

For macOS launchd:

```bash
scripts/install_launchd_self_improvement.sh
```

For Linux systemd user services:

```bash
scripts/install_systemd_self_improvement.sh
```

The daemon writes stdout and stderr to `logs/self-improvement.*.log`. Logs are ignored by git.

## Required local tools

The configured defaults expect:

- a Python environment with the project dependencies installed;
- Codex CLI at `/Applications/Codex.app/Contents/Resources/codex`, or `AUTORESEARCH_AGENT_COMMAND` set to an equivalent command;
- git access through `/Users/rau/bin/codex-git-proxy`, or `git_binary` changed to another git wrapper;
- network access for the technology radar;
- optional RPA Memory on `http://127.0.0.1:37777`.

## Emergency stop

Stop the daemon through the scheduler, then inspect `.autoresearch/supervisor.jsonl` and the latest worktree under `.autoresearch/worktrees/`.

macOS:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.rpa-harness.self-improvement.plist"
```

Linux:

```bash
systemctl --user stop rpa-harness-self-improvement.service
```
