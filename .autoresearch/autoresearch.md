# Autoresearch: RPA Harness Continuous Improvement

## Objective
Improve RPA Harness reliability with measured, reversible changes.

## Primary Metric
- `artifact_hygiene_score` (unitless, higher is better)

## How To Run
- Benchmark: `bash .autoresearch/autoresearch.sh`
- Checks: `bash .autoresearch/autoresearch.checks.sh`

## Files In Scope
- `tools/`
- `tests/`
- `docs/`
- `harness/memory/`
- `harness/reporting/`
- `harness/rpa/`
- `harness/ai/`
- `.autoresearch/`

## Off Limits
- Raw credentials, `.env`, generated reports/runs/data files.
- Core protected runtime paths unless a reproduced failure and test justify the change.
- Broad rewrites or new dependencies without a measured need.

## Keep Rules
- Keep only when the primary metric improves and checks pass.
- Re-run marginal wins if confidence is low.
- Discard or revert crashes, checks failures, secret leaks, and unmeasured changes.

## Codex Session Handoff
The runner writes `.autoresearch/codex_prompt.md` for the next implementation session.
Codex makes one scoped change, then stops. The runner measures and decides keep/discard.

## Always-On Supervisor
The periodic supervisor is configured in `.autoresearch/autoresearch.supervisor.json`.
It scans code, failure reports, and RPA Memory; runs read-only scout subagents for code, failure, and test-gap analysis; creates an isolated worktree; asks Codex to make one scoped improvement; runs autoresearch measurement; reviews the diff; commits kept work; fast-forward merges to `main`; reruns checks; and pushes when every gate passes.

Generated supervisor state lives in `.autoresearch/supervisor.jsonl`, `.autoresearch/supervisor_plan.md`, `.autoresearch/review.md`, `.autoresearch/review.json`, `.autoresearch/autoresearch.learnings.md`, and `.autoresearch/worktrees/`.

## What's Been Tried
- Baseline not recorded yet.
