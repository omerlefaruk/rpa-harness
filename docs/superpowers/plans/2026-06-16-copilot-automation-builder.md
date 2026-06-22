# Copilot Automation Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one copilot assistant surface that gradually creates, validates, runs, reviews, and repairs automations using the existing `rpa-harness` features.

**Architecture:** Add a thin `CopilotSession` state machine over the existing builder, selector swarm, YAML validator, preflight, runtime, repair, reporting, and dashboard APIs. The copilot writes file-backed session artifacts and asks questions at uncertainty/risk gates instead of inventing behavior or bypassing policy.

**Tech Stack:** Python stdlib, existing `HarnessConfig`, `YamlWorkflowRunner`, builder helpers, selector repair/swarm, FastAPI dashboard, React dashboard.

---

## Recommendation

Do not give an agent raw uncontrolled access to every tool as the product boundary. Give it one command manifest, one policy file, and one session state machine:

- **Tools:** existing CLI/runtime features stay as deterministic commands.
- **Hooks:** enforce safety gates before external writes, weak selectors, missing checks, or missing secrets.
- **Skills:** teach the agent how to use the harness, but do not make skills the source of truth.
- **Dashboard:** shows live session state, questions, run evidence, and reports.

The first shippable version should build from known workflow files and discovery evidence. Full natural-language workflow synthesis can come after the session loop is stable.

## File Structure

- Modify: `harness/copilot.py`
  - Keep runtime checkpoint behavior.
  - Add reusable question append/read helpers if needed.
- Create: `harness/copilot_session.py`
  - Own file-backed copilot session state and phase transitions.
  - Call existing helpers instead of duplicating workflow, reporting, or repair logic.
- Modify: `main.py`
  - Add `--copilot-build`, `--copilot-session`, `--copilot-answer`, and `--copilot-advance`.
- Modify: `.agents/config/agent_command_manifest.json`
  - Add the copilot commands so agents discover one supported automation-building flow.
- Modify: `harness/reporting/dashboard.py`
  - Add session list/detail/question endpoints over `builder_sessions/`.
- Modify: `frontend/src/api/client.ts`
  - Add copilot session API types and calls.
- Modify: `frontend/src/App.tsx`
  - Add one `Copilot` tab showing phase status, next question, answers, artifacts, and linked run/report.
- Test: `tests/test_copilot_session.py`
  - Cover state transitions, question gates, answer handling, validation/preflight/run orchestration, and redaction.

---

### Task 1: Session State Spine

**Files:**
- Create: `harness/copilot_session.py`
- Test: `tests/test_copilot_session.py`

- [ ] **Step 1: Write failing tests for start/status/answer**

```python
from pathlib import Path

from harness.copilot_session import answer_copilot_question, read_copilot_session, start_copilot_session


def test_start_copilot_session_creates_redacted_state(tmp_path):
    task = tmp_path / "task.md"
    task.write_text("Build login with password=secret-value\nworkflow: workflow.yaml\n", encoding="utf-8")

    session = start_copilot_session(task, root_dir=tmp_path, session_id="s1")

    state = read_copilot_session("s1", root_dir=tmp_path)
    assert session.name == "s1"
    assert state["status"] == "waiting"
    assert state["phase"] == "intake"
    assert state["next_question"]["id"] == "intake.confirm_scope"
    assert "secret-value" not in Path(state["task_spec"]).read_text(encoding="utf-8")


def test_answer_copilot_question_records_answer_and_advances(tmp_path):
    task = tmp_path / "task.md"
    task.write_text("Build noop automation\nworkflow: workflow.yaml\n", encoding="utf-8")
    start_copilot_session(task, root_dir=tmp_path, session_id="s1")

    state = answer_copilot_question("s1", "intake.confirm_scope", "continue", root_dir=tmp_path)

    assert state["phase"] == "discovery"
    assert state["status"] == "ready"
    assert state["next_question"] is None
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py -q
```

Expected: import fails because `harness.copilot_session` does not exist.

- [ ] **Step 3: Implement the smallest session module**

Implement `start_copilot_session`, `read_copilot_session`, and `answer_copilot_question` using `builder.create_builder_session`, JSON files, JSONL answers, and `redact_value`.

Store:

- `builder_sessions/<id>/copilot_state.json`
- `builder_sessions/<id>/questions.jsonl`
- `builder_sessions/<id>/answers.jsonl`

Initial phases:

- `intake`
- `discovery`
- `draft`
- `validate`
- `preflight`
- `safe_run`
- `review`
- `promoted`

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py -q
```

Expected: `2 passed`.

---

### Task 2: CLI Commands For Agent Use

**Files:**
- Modify: `main.py`
- Modify: `.agents/config/agent_command_manifest.json`
- Test: `tests/test_copilot_session.py`

- [ ] **Step 1: Add CLI smoke tests**

Append tests that call:

```bash
.venv\Scripts\python.exe main.py --copilot-build task.md --builder-session-id s1
.venv\Scripts\python.exe main.py --copilot-session s1
.venv\Scripts\python.exe main.py --copilot-answer s1 --copilot-question-id intake.confirm_scope --copilot-response continue
```

Assert each command returns JSON and never prints secret values.

- [ ] **Step 2: Add argparse flags**

Add flags to `parse_args()`:

```python
parser.add_argument("--copilot-build", help="Start a phase-by-phase copilot automation build from a task markdown file")
parser.add_argument("--copilot-session", help="Show a copilot builder session JSON state")
parser.add_argument("--copilot-answer", help="Answer a copilot session question")
parser.add_argument("--copilot-question-id", help="Question id for --copilot-answer")
parser.add_argument("--copilot-response", help="Answer text for --copilot-answer")
parser.add_argument("--copilot-advance", help="Advance a copilot session to the next automatic phase")
```

- [ ] **Step 3: Wire commands in `main()`**

Call `harness.copilot_session` helpers and print JSON. Exit nonzero only for blocked/failed states.

- [ ] **Step 4: Update the command manifest**

Add commands:

- `copilot_build`
- `copilot_session`
- `copilot_answer`
- `copilot_advance`

- [ ] **Step 5: Run tests**

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py tests/test_autopilot.py -q
```

Expected: all pass.

---

### Task 3: Automatic Phase Runner

**Files:**
- Modify: `harness/copilot_session.py`
- Test: `tests/test_copilot_session.py`

- [ ] **Step 1: Write failing orchestration tests**

Create a noop workflow in `tmp_path`, start a copilot session, answer intake, call `advance_copilot_session()` repeatedly, and assert:

- `validate` records validation output.
- `preflight` records preflight output.
- `safe_run` records `run_dir` and `report`.
- risky workflows stop with a question before external writes.

- [ ] **Step 2: Implement `advance_copilot_session`**

Use existing code only:

- `load_workflow_yaml`
- `validate_workflow_report`
- `load_autopilot_policy`
- `YamlWorkflowRunner.preflight`
- `YamlWorkflowRunner.run`
- existing policy checks from `harness.autopilot`

Do not duplicate runner, report, selector, or retry logic.

- [ ] **Step 3: Add risk gates**

Ask a question and stop when any of these are true:

- workflow path missing
- missing input file
- missing secret
- selector strategy is coordinate
- external write or approval-gated action exists
- validation has errors

- [ ] **Step 4: Run tests**

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py tests/test_workflow_schema.py -q
```

Expected: all pass.

---

### Task 4: Browser Discovery Integration

**Files:**
- Modify: `harness/copilot_session.py`
- Modify: `.agents/config/agent_command_manifest.json`
- Test: `tests/test_copilot_session.py`

- [ ] **Step 1: Add target URL parsing tests**

For a task containing:

```markdown
target_url: file:///C:/example/form.html
intent: Submit
```

assert the discovery phase records a browser selector swarm artifact path and moves to `draft`.

- [ ] **Step 2: Implement discovery phase**

If `target_url` exists in the task spec, call `run_browser_selector_swarm()` with:

- `wait_until="domcontentloaded"`
- `intent` from task when present
- `safe_click=False` by default
- raw HTML saved only when policy allows it

- [ ] **Step 3: Store artifacts**

Write discovery output under the same session directory:

- `discovery/browser_selector_swarm.json`
- linked screenshot/report paths from the swarm result

- [ ] **Step 4: Run browser capability proof**

Run:

```bash
.venv\Scripts\python.exe main.py --copilot-build docs\operator_workflow.md --builder-session-id copilot-local-proof
.venv\Scripts\python.exe main.py --copilot-answer copilot-local-proof --copilot-question-id intake.confirm_scope --copilot-response continue
.venv\Scripts\python.exe main.py --copilot-advance copilot-local-proof
```

Expected: session reaches `draft` or a clear blocked question with discovery artifacts.

---

### Task 5: Dashboard Copilot Tab

**Files:**
- Modify: `harness/reporting/dashboard.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Add API tests**

Test:

- `GET /api/copilot/sessions`
- `GET /api/copilot/sessions/{session_id}`

Use a temp `builder_sessions/<id>/copilot_state.json` fixture.

- [ ] **Step 2: Add dashboard endpoints**

Return only redacted file-backed state. Do not create a second session store.

- [ ] **Step 3: Add frontend API calls**

Add:

```ts
getCopilotSessions: () => getJson<{ sessions: CopilotSession[] }>("/api/copilot/sessions"),
getCopilotSession: (sessionId: string) => getJson<CopilotSession>(`/api/copilot/sessions/${encodeURIComponent(sessionId)}`),
```

- [ ] **Step 4: Add `Copilot` tab**

Show:

- session id
- phase
- status
- next question
- answers
- artifacts
- linked run report

- [ ] **Step 5: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: Vite build succeeds.

---

### Task 6: Real Headed Workflow Proof

**Files:**
- Modify only if proof exposes a bug.

- [ ] **Step 1: Start dashboard**

Run:

```bash
.venv\Scripts\python.exe main.py --serve --port 8080
```

- [ ] **Step 2: Run local browser workflow through copilot**

Use:

```bash
.venv\Scripts\python.exe main.py --copilot-build docs\operator_workflow.md --builder-session-id copilot-local-form
.venv\Scripts\python.exe main.py --copilot-answer copilot-local-form --copilot-question-id intake.confirm_scope --copilot-response continue
.venv\Scripts\python.exe main.py --copilot-advance copilot-local-form
```

When the session asks before risky or uncertain work, answer through `--copilot-answer` and continue.

- [ ] **Step 3: Open dashboard in the in-app browser**

Open:

```text
http://127.0.0.1:8080/app/
```

Capture screenshots of:

- Copilot tab
- Run Detail tab
- report.html

- [ ] **Step 4: Final verification**

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_copilot_session.py tests/test_autopilot.py tests/test_workflow_schema.py tests/test_dashboard.py -q
cd frontend
npm run build
git diff --check
```

Expected:

- tests pass
- frontend build passes
- `git diff --check` is clean
- dashboard shows copilot state and latest run/report

---

## Self-Review

- Spec coverage: one copilot agent surface, automatic CLI-driven operation, questions at uncertainty/risk, browser/CDP-compatible workflow execution, phase-by-phase automation building, dashboard visibility.
- Placeholder scan: no implementation step depends on an unnamed future system.
- Type consistency: session id, question id, phase, status, artifacts, run id, and report are the shared fields across CLI, backend, and frontend.

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-06-16-copilot-automation-builder.md`.

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session with checkpoints.
