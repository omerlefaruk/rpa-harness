# Autoresearch: RPA Harness Continuous Improvement

## Objective
Continuously improve RPA Harness reliability, speed, evidence quality, autonomy, tests, documentation, and technology adoption with measured, reversible changes.

## Primary Metric
- `artifact_hygiene_score` (unitless, higher is better)

## How To Run
- Benchmark: `bash .autoresearch/autoresearch.sh`
- Checks: `bash .autoresearch/autoresearch.checks.sh`
- One free cycle: `python main.py --self-improve-once`
- Continuous free daemon: `python main.py --self-improve-24-7`

## Files In Scope
Free mode uses repository-scope mutation. The agent may edit source, tests, docs, scripts, workflows, configs, project metadata, and autoresearch files when a heartbeat candidate justifies it.

Discovery focuses on:

- `harness/`
- `tools/`
- `tests/`
- `docs/`
- `scripts/`
- `subagents/`
- `workflows/`
- `config/`
- `.autoresearch/`
- `.agents/`
- top-level CLI and project metadata files

## Off Limits
- Raw credentials, `.env`, `.env.local`, and any credential-bearing files.
- Generated reports, runs, screenshots, downloads, logs, local databases, virtual environments, git internals, caches, and build artifacts.
- Broad rewrites that cannot be verified quickly.
- New dependencies without a measured need and a focused test/check path.

## Keep Rules
- Keep only when the primary metric improves and checks pass.
- Discard or revert crashes, checks failures, secret leaks, generated-artifact mutations, and unmeasured changes.
- Post-merge checks must pass on `main`; otherwise the supervisor rolls back to the pre-merge SHA.

## Codex Session Handoff
The runner writes `.autoresearch/codex_prompt.md` for implementation context when used directly. The supervisor builds its own repository-scope prompt and gives Codex a free-mutation cycle. Codex edits the worktree; the supervisor owns commit, merge, push, audit, and rollback.

## Always-On Supervisor
The periodic supervisor is configured in `.autoresearch/autoresearch.supervisor.json`; the same free profile is available as `.autoresearch/autoresearch.sovereign.json`.

It scans code, failure reports, technology-radar candidates, and RPA Memory; runs read-only scout subagents for code, failure, speed, and technology-adoption analysis; creates an isolated worktree; asks Codex to make a coherent repository-scope improvement; runs autoresearch measurement; skips automated review when `require_review=false`; commits kept work; fast-forward merges to `main`; reruns checks; and pushes when configured.

Generated supervisor state lives in `.autoresearch/supervisor.jsonl`, `.autoresearch/supervisor_plan.md`, `.autoresearch/review.md`, `.autoresearch/review.json`, `.autoresearch/autoresearch.learnings.md`, and `.autoresearch/worktrees/`.

## What's Been Tried
- Baseline not recorded yet.
