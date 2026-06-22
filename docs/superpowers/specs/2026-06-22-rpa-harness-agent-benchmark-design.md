# RPA Harness Agent Benchmark Design

## Goal

Create a small benchmark that measures whether agent-assisted workflow creation and repair gets cheaper, faster, and more accurate over time.

The benchmark must measure the expensive loop first: prompt -> agent/tool work -> generated or repaired workflow -> deterministic harness validation/run -> evidence artifacts.

## Non-goals

- No new benchmark server, database, dashboard, or external platform.
- No generic academic leaderboard.
- No LLM judge in the first slice.
- No real destructive external writes.

## Borrowed patterns

- OSWorld: each task has setup plus an execution-based evaluator.
- WebArena and WorkArena: replayable tasks with captured trajectories.
- BrowserGym: one runner interface over multiple task types.
- tau-bench: repeat trials and pass rates for tool-using agents.
- SWE-bench: JSONL records in, deterministic checks out.
- AgentRewardBench: track success, side effects, and repetition separately.

## Benchmark shape

```text
benchmarks/
  tasks/
    browser_happy_path.json
    browser_selector_repair.json
    invalid_missing_success_check.json
  fixtures/
  README.md

runs/benchmarks/<run_id>/
  results.jsonl
  summary.json
```

Each task file defines:

```json
{
  "id": "browser_happy_path",
  "kind": "agent_workflow_build",
  "prompt": "Build and run the workflow from this fixture.",
  "fixture": "benchmarks/fixtures/browser_happy_path",
  "expected": {
    "workflow_validates": true,
    "run_succeeds": true,
    "required_artifacts": [
      "run_manifest.json",
      "timeline.jsonl",
      "report.html"
    ]
  },
  "limits": {
    "max_tool_calls": 40,
    "max_wall_seconds": 600
  }
}
```

## First task lanes

1. Happy path: agent builds a valid workflow from a fixed prompt and fixture.
2. Repair path: agent fixes a known selector or data issue using existing evidence.
3. Safety/validation path: agent must reject or fix an invalid workflow with missing success checks.

These three lanes are enough. More tasks come only after the runner proves useful.

## Metrics

Each benchmark attempt writes one `results.jsonl` row:

```json
{
  "run_id": "bench-20260622-001",
  "task_id": "browser_happy_path",
  "trial": 1,
  "success": true,
  "accuracy_score": 1.0,
  "wall_seconds": 123.4,
  "tool_calls": 18,
  "input_tokens": 42000,
  "output_tokens": 6200,
  "retries": 1,
  "evidence_complete": true,
  "side_effects": false,
  "loop_detected": false,
  "notes": ""
}
```

`summary.json` aggregates:

- pass rate
- mean wall seconds
- mean tool calls
- mean tokens
- evidence completeness rate
- side-effect count
- loop count

## Scoring

The first version uses deterministic scoring only:

- `success`: workflow validates and expected run result passes.
- `accuracy_score`: `1.0` for full pass, `0.5` for valid workflow but failed run, `0.0` otherwise.
- `evidence_complete`: all required artifacts exist and are readable.
- `side_effects`: true when a task performs a forbidden or unapproved action.
- `loop_detected`: true when repeated tool/action patterns exceed a simple threshold.

Token counts are recorded when the agent runtime exposes them. Missing token data is written as `null`, not guessed.

## Runner

Add one boring CLI entry later:

```text
python -m harness.benchmark run --tasks benchmarks/tasks --out runs/benchmarks
```

The runner should:

1. Load task JSON files.
2. Create a benchmark run folder.
3. Execute each task for `--trials N`.
4. Collect tool-call, token, timing, retry, and evidence metrics.
5. Write `results.jsonl` and `summary.json`.
6. Exit non-zero when pass rate or safety checks fail configured thresholds.

## Data flow

```text
task.json
  -> benchmark runner
  -> agent-assisted build/repair loop
  -> harness validate/run
  -> existing run artifacts
  -> deterministic evaluator
  -> results.jsonl + summary.json
```

Existing artifacts remain the source of truth:

- `run_manifest.json`
- `timeline.jsonl`
- `evidence_bundle.json`
- `repair_packet.json`
- `report.html`

## Error handling

- Invalid task JSON fails before running any agent work.
- Missing fixture fails that task with `success=false`.
- Missing token usage does not fail the task; it records `null`.
- Missing evidence artifacts fails `evidence_complete`.
- Forbidden side effects fail the task even if the workflow output looks correct.

## Testing plan

Minimum checks for the first implementation:

- one unit test for task loading and validation
- one unit test for summary aggregation
- one smoke test using a fake agent result and fake run artifacts

No browser automation is required for the benchmark runner tests. Real browser tasks can be benchmark fixtures later.

## Acceptance criteria

- A developer can run the benchmark from one command.
- Results are reproducible from fixed task files and fixtures.
- Results are inspectable without a server.
- The first suite contains exactly three task lanes.
- The benchmark reports tool calls, tokens when available, speed, accuracy, and evidence completeness.
- Existing rpa-harness run artifacts remain the truth; the benchmark does not create a parallel observability store.
