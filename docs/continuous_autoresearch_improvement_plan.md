# Continuous Autoresearch Improvement Plan

## Inputs Reviewed

- Local RPA Memory service evidence from `/api/search`, `/api/timeline`, and `/api/observations/batch`.
- Current harness architecture docs, agent rules, memory policy, capability plan, YAML runner, agent loop, memory client/server/store, and config.
- `karpathy/autoresearch`: narrow edit surface, fixed measurement budget, one primary metric, keep/discard loop, and simple agent instructions in `program.md`.
- `davebcn87/pi-autoresearch`: domain-agnostic experiment tools, append-only JSONL history, restart-safe session markdown, correctness checks, confidence score, hooks, live dashboard, and resumable long-running loop.

## Current Harness Facts

- RPA Memory is running locally on `127.0.0.1:37777`.
- Recent memory has verified YAML API, browser/API, Excel, and real API/Excel benchmark runs.
- Recent memory also has failure evidence for API status-code failures, missing Excel inputs, and the macOS boundary for Windows UIAutomation.
- The repo already has a capability characterization plan with two main remaining gaps: Windows desktop proof and explicit memory deployment/health-check docs.
- The current worktree is dirty. Any future implementation must first isolate an improvement branch and avoid overwriting unrelated changes.

## Chosen Direction

Build a harness-native autoresearch loop, but keep it outside protected runtime code at first.

The first implementation should live in `tools/` or `scripts/` and use existing CLI, tests, reports, RPA Memory, and git. Only after it proves value should pieces move into `harness/`.

This keeps the self-improvement system deterministic: every accepted change must have a measured improvement, passing checks, clean evidence, and a recorded lesson.

## Core Loop

Each iteration runs:

1. Rehydrate context from session files, RPA Memory, current git state, and recent failure reports.
2. Pick one small hypothesis.
3. Modify only the allowed files for that experiment.
4. Run the benchmark command and parse structured `METRIC name=value` lines.
5. Run correctness checks separately from the primary metric.
6. Keep only if the metric improves and checks pass.
7. Revert if worse, equal without simplification, crashed, or checks failed.
8. Append the run result, hypothesis, learned lesson, failure category, and next focus to JSONL and RPA Memory.
9. Run heartbeat checks before the next iteration.

## Autonomous Integration Loop

The target mode is fully autonomous after the session is configured:

1. Create an isolated `autoresearch/<session-id>` branch and matching git worktree.
2. Run each experiment inside the worktree, never in the user's active checkout.
3. Commit kept experiments in the worktree branch with the metric, checks result, and lesson in the commit message.
4. Revert or reset discarded, crashed, or checks-failed experiments inside the worktree only.
5. Run an automated code-review gate over the kept diff before integration.
6. Merge to `main` automatically only when every merge gate passes.
7. Push `main` only after the local merge, checks, and post-merge smoke run succeed.

Automatic merge is allowed only for changes that stay inside the configured allowed paths, improve the primary metric, pass correctness checks, pass review, contain no secret/report/data artifacts, and preserve a clean post-merge working tree.

Automatic merge must stop instead of forcing through when protected runtime files are touched, review finds a blocking issue, tests fail, the branch is behind `main`, merge conflicts appear, generated artifacts are staged, secrets are detected, or the improvement is inside benchmark noise.

## Always-On Supervisor

Run `tools/autoresearch_supervisor.py` as the periodic control loop. It is responsible for:

1. Running heartbeat before every cycle.
2. Searching the codebase for improvement candidates such as TODO/FIXME markers, recent failure reports, and RPA Memory matches.
3. Spawning read-only scout subagents in parallel to inspect allowed paths and propose focused improvements.
4. Merging scout proposals with deterministic candidates and writing `.autoresearch/supervisor_plan.md` with the next scoped experiment prompt.
5. Starting Codex in the isolated worktree to implement exactly one small improvement.
6. Running the deterministic autoresearch benchmark/check judge.
7. Running automated review against the uncommitted worktree diff.
8. Committing kept work, fast-forward merging to `main`, rerunning post-merge checks, and pushing when configured.
9. Appending `.autoresearch/supervisor.jsonl` and saving a compact lesson to RPA Memory.

The supervisor is configured by `.autoresearch/autoresearch.supervisor.json`. The default interval is one hour. Worktrees live under `.autoresearch/worktrees/` and are ignored by git.

The default scout subagents are `code_explorer`, `failure_analyst`, and `test_gap_planner`. They run through Codex CLI with a read-only sandbox, produce JSON candidates only, and cannot bypass the existing autoresearch benchmark, integration gate, automated review, post-merge checks, or push gate.

## Session Files

Use these files at the repo root or under `.autoresearch/`:

- `autoresearch.md`: objective, metric, scope, off-limits files, constraints, tried ideas, wins, dead ends.
- `autoresearch.jsonl`: append-only run log with metric, status, commit, confidence, checks result, hypothesis, learned lesson, and failure category.
- `autoresearch.sh`: benchmark script that prints structured metrics.
- `autoresearch.checks.sh`: correctness backpressure: compile, focused tests, full tests when needed, secret/report redaction checks.
- `autoresearch.ideas.md`: backlog of untried ideas.
- `autoresearch.hooks/before.sh`: memory lookup, web/source refresh, anti-thrash, idea rotation.
- `autoresearch.hooks/after.sh`: learnings journal, memory save, optional notification, winner tagging.

## First Primary Metrics

Start with reliability before speed:

- `capability_pass_rate`: higher is better.
- `failure_report_score`: higher is better, based on required evidence fields present.
- `memory_retrieval_score`: higher is better, based on search -> timeline -> details finding useful observations.
- `default_cli_seconds`: lower is better, after reliability is stable.
- `agent_mock_success_rate`: higher is better for deterministic mocked-agent tasks.

Do not optimize broad runtime speed until correctness and evidence quality are stable.

## Heartbeat Checks

Run before every iteration and every few minutes during long commands:

- Memory health: `GET /health` must return ok unless the session explicitly permits memory-off mode.
- Git health: branch is expected, no unrelated dirty files outside allowed scope.
- Process health: benchmark is still producing output or within timeout.
- Disk health: reports/runs/data are not growing without bound.
- Budget health: max iterations, max wall-clock, and optional token/cost limits are respected.
- Correctness health: last kept run has passing checks.
- Evidence health: failures include report path, step id, action type, error, and sanitized artifacts.
- Secret health: no raw secrets in reports, memory, JSONL, screenshots metadata, or logs.
- Thrash health: repeated discards trigger a strategy change instead of small variations.
- Noise health: re-run marginal wins when confidence is below threshold.

## Before Hook Ideas

- Query RPA Memory for similar failures and prior fixes using the 3-layer pattern.
- Search current upstream docs or GitHub repos only for the narrow target being optimized.
- Rotate ideas from `autoresearch.ideas.md`.
- Trigger anti-thrash after repeated discards.
- Refresh context after compaction or restart by reading the session files and recent git log.

## After Hook Ideas

- Save one stable lesson per run to RPA Memory.
- Append a human-readable line to `autoresearch.learnings.md`.
- Tag new best commits with sortable tags.
- Update dashboard state.
- If a failure repeats, add a specific backlog item instead of retrying the same shape.

## Safety Gates

- Protected areas still require the mutation protocol.
- No raw credentials in any experiment artifact.
- No destructive external actions in improvement loops.
- No new dependency unless an experiment explicitly targets dependency adoption and checks prove it.
- No broad rewrites. Each experiment owns a small file set.
- No accepting improvements from noisy metrics without confidence or confirmation re-run.
- No permanent code change without tests or a documented reason why the change is doc-only.
- No automatic merge unless the isolated worktree branch passes benchmark, checks, automated code review, merge-conflict detection, secret scan, artifact hygiene, and post-merge smoke verification.
- No automatic push unless the local `main` merge is clean and the remote has not advanced unexpectedly.

## Implementation Phases

### Phase 1: Planner Only

- Keep this document as the operating plan.
- Create a template `autoresearch.md`, `autoresearch.sh`, and `autoresearch.checks.sh` for this repo.
- Define the first benchmark command around existing capability tests and memory health.

### Phase 2: Manual Loop

- Run 5-10 supervised experiments manually.
- Record every run in JSONL and RPA Memory.
- Validate keep/discard rules and confidence scoring with real local data.

### Phase 3: Runner Script

- Add `tools/autoresearch_runner.py`.
- Responsibilities: load config, run benchmark, parse metrics, run checks, write JSONL, call RPA Memory, and enforce heartbeat gates.
- Keep git mutation behind `/Users/rau/bin/codex-git-proxy`.

### Phase 4: Dashboard

- Extend reporting with an autoresearch view showing run count, best metric, confidence, checks failures, failure categories, and latest heartbeat.
- Start read-only. Do not add control buttons until the loop is stable.

### Phase 5: Harness Integration

- Add first-class CLI only after the external runner proves useful.
- Candidate command: `python main.py --autoresearch --config autoresearch.config.yaml`.
- Keep implementation thin: CLI delegates to the proven runner.

### Phase 6: Agent Improvement Track

- Improve planner prompts and tool selection using measured mocked-agent tasks.
- Add stricter success-check enforcement for every agent-generated step.
- Add a recovery classifier that maps failures to selector, timing, credential, app-down, business-rule, platform-boundary, and harness-bug categories.
- Record per-step decision quality in RPA Memory.

### Phase 7: Meta-Improvement

- Allow the loop to optimize its own idea-selection and hook strategy, but not protected harness code directly.
- Evaluate search strategies by whether they produce kept improvements, fewer repeated failures, and faster root-cause classification.

### Phase 8: Autonomous Review, Merge, and Push

- Add isolated worktree orchestration for each autoresearch session.
- Add a review command that classifies findings as blocking or non-blocking and writes a machine-readable review report.
- Add an integration command that rebases or updates from `main`, runs the merge dry-run, merges only clean reviewed branches, reruns checks on `main`, and pushes through `/Users/rau/bin/codex-git-proxy`.
- Keep a full append-only audit trail in JSONL and RPA Memory: branch, worktree, commit, metric, review result, merge result, push result, and rollback hint.

## First Experiments To Run

1. Memory health and retrieval quality: improve search/context scoring so `api`, `excel`, and `desktop` queries retrieve the most useful prior observations.
2. Failure report completeness: score failed YAML runs against the failure-report schema and fill missing evidence.
3. Windows desktop boundary handling: make the macOS unsupported path more actionable while preserving a Windows proof backlog.
4. Agent mocked-flow reliability: ensure agent plans always include success checks and stop conditions.
5. Report/data hygiene: prove generated artifacts stay ignored and redacted.

## Acceptance Criteria

- A fresh agent can resume the loop from session files plus RPA Memory.
- Every kept change has a metric, checks result, commit hash, and lesson.
- Every discarded/crashed run preserves what was tried and why it failed.
- Heartbeat failure stops or pauses the loop predictably.
- The default harness verification remains green.
- Automatic review, commit, merge, and push are allowed only after all configured gates pass and the final `main` verification succeeds.
- The plan improves the harness without weakening deterministic execution or credential safety.
