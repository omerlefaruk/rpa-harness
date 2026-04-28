# Autoresearch: RPA Harness Continuous Improvement

## Objective
Improve RPA Harness reliability with measured, reversible changes.

## Primary Metric
- `capability_pass_rate` (unitless, higher is better)

## How To Run
- Benchmark: `bash .autoresearch/autoresearch.sh`
- Checks: `bash .autoresearch/autoresearch.checks.sh`

## Files In Scope
- `tools/`
- `tests/`
- `docs/`
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

## What's Been Tried
- Baseline not recorded yet.
