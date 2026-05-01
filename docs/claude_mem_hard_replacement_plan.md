# RPA Memory Hard Replacement Plan

## Investigation and Source Attribution

- Source investigated: `thedotmack/claude-mem`
- Local clone: `/tmp/claude-mem.nEus0x/repo`
- Cloned commit: `7e2da10` (`main`, `v12.4.8`)
- Latest release observed through `gh`: `v12.4.8`, published 2026-04-28
- Stack: TypeScript, Node/Bun, Express, `bun:sqlite`, optional Chroma vector search, Claude/Gemini/OpenRouter worker agents
- License: AGPL-3.0

Claude-Mem is not a Python package. It is a long-running memory sidecar plus hooks, HTTP API, SQLite store, search endpoints, and optional Chroma sync. The RPA Harness will not vendor or wrap that runtime as a product dependency. The local feature name is **RPA Memory**.

The target implementation is a local Python RPA Memory service/client inspired by the cloned upstream architecture: sessions, durable observations, summaries, prompt history, queued processing, search, timeline-style retrieval, and context injection. This is a hard replacement for the existing `harness.memory` package, not a compatibility facade.

## Current Harness Memory To Remove

Current long-term memory is a local Python adaptation with these responsibilities:

- `harness/memory/database.py`: SQLite tables for `sessions`, `observations`, `selector_cache`, `error_patterns`, `session_context`
- `harness/memory/engine.py`: `RPAMemory` session lifecycle, selector cache, error learning, context injection
- `harness/memory/search.py`: 3-layer local search wrapper
- `harness/memory/inject.py`: local prompt context formatter
- `harness/memory/compress.py`: OpenAI summary generation
- `harness/memory/hooks.py`: step/session capture helper
- `harness/memory/server.py`: FastAPI worker on port `38777`
- `harness/ai/tools.py`: old `memory_search` tool
- `harness/ai/agent.py`: optional `memory_engine.inject_context()` and `capture_session()`
- `main.py`: `--memory-serve` and `--memory-port`
- `config/default.yaml` and `harness/config.py`: current `memory` config shape
- Tests that depend on `MemoryDatabase`: `tests/test_memory.py` and memory sections in `tests/capabilities/test_recovery_selector_memory_capabilities.py`
- Docs mentioning current memory worker/schema: `SKILL.md`, `docs/architecture.md`, dashboard copy, mutation/memory policy references

Keep `harness/ai/memory.py` only as short-term in-process step history, but rename it in the same migration to something explicit like `AgentStepHistory`. It is not long-term memory and should not share the word "memory" after the cutover.

## Target RPA Memory Model

Implement the memory model in Python with these first-class records:

- Sessions: automation suite, workflow, YAML run, or agent run lifecycle
- Observations: durable, redacted evidence from verified steps, failures, selector healing, mismatches, and final outcomes
- Summaries: compact session summaries for later retrieval and context injection
- Prompts: user/task prompts associated with sessions
- Queue: pending summarization/indexing work
- Search: keyword search, timeline retrieval, observation lookup, and context injection
- Viewer: local RPA Memory viewer on its configured localhost port

RPA-specific selector/error/cache concepts should become normal RPA Memory observations with metadata and concepts, not separate first-class tables. No `selector_cache`, no `error_patterns`, no old `search_type=selector|workflow|error`.

## Chosen Approach

Build a local Python RPA Memory service and client in this repo.

Reason:

- This repo is Python; the memory runtime should match the existing harness runtime and test stack.
- The investigated upstream source is AGPL-3.0. Do not copy, vendor, or modify its source inside this project without a license decision.
- A local implementation keeps deployment simple for automation runs while adopting the useful architectural concepts.
- The harness can keep deterministic automation logic in Python while treating long-term memory as a local service boundary.

Do not add old-API compatibility. The replacement stays under `harness/memory/`, but every exported class and endpoint now follows the new RPA Memory model.

## New Harness Files

Add a new package:

```text
harness/memory/
  __init__.py
  client.py          # async HTTP client for RPA Memory service
  config.py          # MemoryConfig dataclass/env loading
  events.py          # typed session/observation/summary request objects
  recorder.py        # high-level run/test/workflow/agent capture helper
  server.py          # local Python service entrypoint
  store.py           # SQLite persistence and retrieval
```

Core client methods:

- `health()`
- `start_session(content_session_id, project, prompt, platform_source="rpa-harness")`
- `record_observation(content_session_id, tool_name, tool_input, tool_response, cwd, tool_use_id=None, agent_id=None, agent_type=None)`
- `summarize(content_session_id, last_assistant_message)`
- `complete(session_db_id)` if completion is required
- `save_memory(text, title=None, project=None, metadata=None)`
- `search(query=None, project=None, type=None, obs_type=None, limit=20)`
- `timeline(anchor=None, query=None, project=None, depth_before=3, depth_after=3)`
- `get_observations(ids, project=None)`
- `context_inject(project, full=False)`
- `semantic_context(query, project, limit=5)`

Use `httpx.AsyncClient`, tight timeouts, localhost-only defaults, and deterministic redaction with `harness.security` before every request.

## Configuration Cutover

Remove current `MemoryConfig` fields and replace with:

```yaml
memory:
  enabled: true
  worker_url: http://127.0.0.1:37777
  db_path: ./data/rpa_memory.db
  required: false
  project: rpa-harness
  request_timeout_seconds: 2
  semantic_inject: false
  semantic_inject_limit: 5
```

Environment overrides:

- `RPA_MEMORY_ENABLED`
- `RPA_MEMORY_WORKER_URL`
- `RPA_MEMORY_DB`
- `RPA_MEMORY_REQUIRED`
- `RPA_MEMORY_PROJECT`
- `RPA_MEMORY_TIMEOUT`

Failure policy:

- Default: fail open. Automation should continue if the RPA Memory service is down, but logs and reports must show `rpa_memory_status=unavailable`.
- CI/strict mode: if `required=true`, fail fast when `health()` fails before a run.

## Capture Mapping

### Test Runs

In `AutomationHarness.run()`:

- Start one RPA Memory session for the full suite.
- Record each test completion as an observation.
- Record final suite summary.

In `AutomationTestCase._execute()`:

- Do not record every `step()` call unless there is result evidence.
- Record final test status, duration, error, stack trace summary, screenshots, logs, and metadata.

### RPA Workflows

In `RPAWorkflow._execute()`:

- Start a session for the workflow.
- Record setup, record-processing aggregate, teardown, and final workflow result.
- Record record-level failures and mismatches as observations.
- Do not store raw record values without redaction.

### YAML Workflows

In `YamlWorkflowRunner.run()`:

- Start a session using workflow id/name as prompt.
- Record each YAML step result after success checks complete.
- Include `checks`, `status`, `attempts`, `destructive`, failure report path, and redacted evidence.
- Summarize on pass/fail before closing drivers.

### Agent Mode

In `RPAAgent.execute()`:

- Replace `memory_engine.inject_context()` with `MemoryClient.semantic_context()` or `context_inject()`.
- Replace `capture_session()` with `summarize()` plus a final observation containing the agent summary.
- Replace old `memory_search` tool with RPA Memory-native tools:
  - `mem_search`
  - `mem_timeline`
  - `mem_get_observations`

### Selector Healing

Do not recreate `selector_cache`. When a selector succeeds, heals, or fails, record an observation with:

- `tool_name`: `selector`
- `tool_input`: selector candidate, selector type, URL pattern
- `tool_response`: success/failure, healed selector, verification result
- metadata concepts: `selector`, `healing`, `browser`

Future agents should retrieve this with RPA Memory search, not direct selector lookup.

## Removal Steps

1. Create a branch before edits.
2. Confirm current dirty worktree and avoid overwriting unrelated user changes.
3. Delete `harness/memory/`.
4. Remove `--memory-serve` and `--memory-port` from `main.py`.
5. Replace old `MemoryConfig` fields and `memory:` YAML contents with RPA Memory service settings.
6. Remove `memory_engine` parameters from `AutomationHarness.run_agent()`, `RPAAgent`, and `build_default_tools()`.
7. Rename short-term `harness/ai/memory.py` to `harness/ai/step_history.py`.
8. Replace `harness/memory/` with the new RPA Memory package.
9. Wire recorder into test, workflow, YAML, and agent execution paths.
10. Replace old memory tests with RPA Memory client/recorder tests.
11. Update docs and skill text to describe the RPA Memory service.
12. Archive old `data/memory.db`; do not read it at runtime.

No dual-write, no dual-read, no legacy import aliases.

## Test Plan

Unit tests:

- `MemoryClient` sends correct requests using `httpx.MockTransport`.
- Service storage persists sessions, observations, summaries, prompts, and queued work.
- Client redacts tokens, cookies, secrets, auth headers, and secret-like assignments before sending.
- Client fail-open behavior returns a structured unavailable result.
- `required=true` turns service health failure into a hard error.
- Search tools call the RPA Memory search, timeline, and observation lookup endpoints.

Integration tests with fake service:

- YAML workflow run records session init, step observations, and summary.
- Failed YAML step records failure report path and redacted error.
- RPA workflow mismatch records one observation without raw secrets.
- Agent mode injects returned context into planning and writes final summary.

Removal tests:

- Importing legacy exports from `harness.memory` fails.
- CLI no longer accepts `--memory-serve`.
- No code references `MemoryDatabase`, `RPAMemory`, `MemoryHooks`, `MemorySearch`, `ContextInjector`, or `MemoryCompressor`.

Commands:

```bash
python3 -m py_compile harness/*.py harness/**/*.py main.py
python3 -m pytest tests/test_memory.py tests/capabilities/test_recovery_selector_memory_capabilities.py
python3 -m pytest tests/test_security.py tests/test_yaml_runner_integration.py
python3 -m pytest
```

Optional local service smoke:

```bash
python main.py --rpa-memory-serve --rpa-memory-port 37777
curl -fsS http://127.0.0.1:37777/health
python main.py --run-yaml workflows/examples/minimal_example.yaml
curl -fsS "http://127.0.0.1:37777/api/search?query=minimal&project=rpa-harness&limit=5"
```

## Acceptance Criteria

- Old memory package is gone.
- Old memory CLI is gone.
- Old SQLite memory schema is no longer created.
- No runtime path reads `data/memory.db`.
- Harness records run/workflow/agent observations into RPA Memory when enabled.
- Harness still runs when RPA Memory is unavailable unless `required=true`.
- Secret redaction happens before every RPA Memory service call.
- Search uses the RPA Memory sessions/observations/summaries/search model only.
- Tests prove both success and service-unavailable paths.
- Docs explain the local service dependency and the hard cutover.

## Risks

- License: do not copy, vendor, or modify upstream source in this repo without a license decision.
- Runtime dependency: memory-enabled runs need the local RPA Memory service process.
- Semantic dependency: semantic search may require an embedding/vector backend if enabled. Keep SQLite-only search documented for reliable local operation.
- Data loss perception: the old `data/memory.db` is not migrated at runtime. If prior memory matters, do a one-time export/import before deletion and then remove the converter.
- Noise/cost: recording every low-level RPA action can flood memory. Record verified step results and failures, not raw polling or transient waits.

## Open Decisions Before Implementation

1. Required mode: should memory be best-effort by default, or required for CI?
2. Project naming: fixed `rpa-harness`, repo-derived, or workflow-derived.
3. Whether semantic search starts SQLite-only or adds a vector backend immediately.
4. Whether old memory history should be archived only or one-time imported.
