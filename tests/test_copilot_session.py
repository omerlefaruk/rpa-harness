import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness.config import HarnessConfig


def _noop_workflow(path: Path) -> None:
    path.write_text(
        """
id: copilot_noop
name: Copilot Noop
version: "1.0"
type: api
steps:
  - id: done
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )


def test_start_copilot_session_creates_redacted_state(tmp_path):
    from harness.copilot_session import read_copilot_session, start_copilot_session

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
    from harness.copilot_session import answer_copilot_question, read_copilot_session, start_copilot_session

    task = tmp_path / "task.md"
    task.write_text("Build noop automation\nworkflow: workflow.yaml\n", encoding="utf-8")
    start_copilot_session(task, root_dir=tmp_path, session_id="s1")

    state = answer_copilot_question("s1", "intake.confirm_scope", "continue", root_dir=tmp_path)

    assert state["phase"] == "discovery"
    assert state["status"] == "ready"
    assert state["next_question"] is None
    assert read_copilot_session("s1", root_dir=tmp_path)["answers"][-1]["answer"] == "continue"


def test_copilot_cli_outputs_json(tmp_path):
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    session_id = f"copilot_cli_{tmp_path.name}"
    _noop_workflow(wf_path)
    task_path.write_text(f"Build and run this automation.\nworkflow: {wf_path}\n", encoding="utf-8")

    started = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--copilot-build",
            str(task_path),
            "--builder-session-id",
            session_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    shown = subprocess.run(
        [sys.executable, "main.py", "--copilot-session", session_id],
        check=True,
        capture_output=True,
        text=True,
    )
    answered = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--copilot-answer",
            session_id,
            "--copilot-question-id",
            "intake.confirm_scope",
            "--copilot-response",
            "continue",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    for completed in (started, shown, answered):
        payload = json.loads(completed.stdout)
        assert payload["session_id"] == session_id
        assert "secret-value" not in completed.stdout


def test_copilot_auto_cli_reaches_review_with_json_only(tmp_path):
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    session_id = f"copilot_auto_{tmp_path.name}"
    _noop_workflow(wf_path)
    task_path.write_text(f"Build and run this automation.\nworkflow: {wf_path}\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--copilot-auto",
            str(task_path),
            "--builder-session-id",
            session_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["session_id"] == session_id
    assert payload["phase"] == "review"
    assert payload["status"] == "waiting"
    assert payload["next_question"]["id"] == "review.promote"
    assert payload["run"]["status"] == "passed"


@pytest.mark.asyncio
async def test_advance_copilot_session_validates_preflights_and_runs(tmp_path, monkeypatch):
    from harness.copilot_session import (
        advance_copilot_session,
        answer_copilot_question,
        start_copilot_session,
    )

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    _noop_workflow(wf_path)
    task_path.write_text(f"Build and run this automation.\nworkflow: {wf_path}\n", encoding="utf-8")
    start_copilot_session(task_path, root_dir=tmp_path, session_id="s1")
    answer_copilot_question("s1", "intake.confirm_scope", "continue", root_dir=tmp_path)

    state = {}
    for _ in range(6):
        state = await advance_copilot_session("s1", root_dir=tmp_path, config=HarnessConfig())
        if state["status"] == "waiting":
            break

    assert state["phase"] == "review"
    assert state["status"] == "waiting"
    assert state["validation"]["errors"] == []
    assert state["preflight"]["status"] == "passed"
    assert state["run"]["status"] == "passed"
    assert Path(state["run"]["run_dir"], "report.html").exists()


@pytest.mark.asyncio
async def test_run_copilot_auto_stops_at_review_for_noop(tmp_path, monkeypatch):
    from harness.copilot_session import run_copilot_auto

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "workflow.yaml"
    task_path = tmp_path / "task.md"
    _noop_workflow(wf_path)
    task_path.write_text(f"Build and run this automation.\nworkflow: {wf_path}\n", encoding="utf-8")

    state = await run_copilot_auto(task_path, root_dir=tmp_path, session_id="s1", config=HarnessConfig())

    assert state["phase"] == "review"
    assert state["status"] == "waiting"
    assert state["next_question"]["id"] == "review.promote"
    assert state["answers"][0]["question_id"] == "intake.confirm_scope"
    assert state["auto"]["status"] == "stopped"
    assert Path(state["artifacts"]["copilot_report_json"]).exists()
    assert Path(state["artifacts"]["copilot_report_md"]).exists()


@pytest.mark.asyncio
async def test_advance_copilot_session_stops_before_risky_external_write(tmp_path, monkeypatch):
    from harness.copilot_session import (
        answer_copilot_question,
        start_copilot_session,
    )

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "risky.yaml"
    task_path = tmp_path / "task.md"
    wf_path.write_text(
        """
id: risky
name: Risky
version: "1.0"
type: api
steps:
  - id: write
    side_effect: external_write
    action:
      type: no_op
    success_check:
      - type: always_pass
""",
        encoding="utf-8",
    )
    task_path.write_text(f"Run it.\nworkflow: {wf_path}\n", encoding="utf-8")
    start_copilot_session(task_path, root_dir=tmp_path, session_id="s1")
    state = answer_copilot_question("s1", "intake.confirm_scope", "continue", root_dir=tmp_path)

    assert state["phase"] == "policy"
    assert state["next_question"]["id"] == "policy.review"
    assert "external writes are disabled" in json.dumps(state["next_question"]["details"])


@pytest.mark.asyncio
async def test_policy_approval_is_bound_to_workflow_hash(tmp_path, monkeypatch):
    from harness.copilot_session import advance_copilot_session, answer_copilot_question, start_copilot_session

    monkeypatch.chdir(tmp_path)
    wf_path = tmp_path / "risky.yaml"
    task_path = tmp_path / "task.md"
    wf_text = """
id: risky
name: Risky
version: "1.0"
type: api
steps:
  - id: write
    side_effect: external_write
    action:
      type: no_op
    success_check:
      - type: always_pass
"""
    wf_path.write_text(wf_text, encoding="utf-8")
    task_path.write_text(f"Run it.\nworkflow: {wf_path}\n", encoding="utf-8")
    start_copilot_session(task_path, root_dir=tmp_path, session_id="s1")
    answer_copilot_question("s1", "intake.confirm_scope", "continue", root_dir=tmp_path)
    answer_copilot_question("s1", "policy.review", "continue", root_dir=tmp_path)
    wf_path.write_text(wf_text.replace("name: Risky", "name: Risky Changed"), encoding="utf-8")

    state = {}
    for _ in range(4):
        state = await advance_copilot_session("s1", root_dir=tmp_path, config=HarnessConfig())
        if state["status"] == "waiting":
            break

    assert state["phase"] == "validate"
    assert state["next_question"]["id"] == "policy.review"


@pytest.mark.asyncio
async def test_advance_copilot_session_runs_browser_discovery(tmp_path, monkeypatch):
    import harness.copilot_session as copilot_session
    from harness.copilot_session import (
        advance_copilot_session,
        answer_copilot_question,
        start_copilot_session,
    )

    async def fake_swarm(url, **kwargs):
        return {
            "status": "passed",
            "url": url,
            "summary": {"interactive_elements": 2, "candidates": 3, "validated": 1},
            "artifacts": {"report": "selector_swarm_report.json", "screenshot": "screenshot.png"},
            "validation": {"winner": {"selector": {"strategy": "role", "role": "button", "name": "Submit"}}},
        }

    monkeypatch.setattr(copilot_session, "run_browser_selector_swarm", fake_swarm)
    task_path = tmp_path / "task.md"
    task_path.write_text(
        "Build browser automation\ntarget_url: file:///C:/example/form.html\nintent: Submit\n",
        encoding="utf-8",
    )
    start_copilot_session(task_path, root_dir=tmp_path, session_id="s1")
    answer_copilot_question("s1", "intake.confirm_scope", "continue", root_dir=tmp_path)

    state = await advance_copilot_session("s1", root_dir=tmp_path, config=HarnessConfig())

    assert state["phase"] == "draft"
    assert state["discovery"]["browser_selector_swarm"]["status"] == "passed"
    assert (tmp_path / "builder_sessions" / "s1" / "discovery" / "browser_selector_swarm.json").exists()


@pytest.mark.asyncio
async def test_advance_copilot_session_reuses_discovery_cache(tmp_path, monkeypatch):
    import harness.copilot_session as copilot_session
    from harness.copilot_session import advance_copilot_session, answer_copilot_question, start_copilot_session

    calls = {"count": 0}

    async def fake_swarm(url, **kwargs):
        calls["count"] += 1
        return {
            "status": "passed",
            "url": url,
            "summary": {"interactive_elements": 2, "candidates": 3, "validated": 1},
            "artifacts": {"report": "selector_swarm_report.json", "screenshot": "screenshot.png"},
            "validation": {"winner": {"selector": {"strategy": "role", "role": "button", "name": "Submit"}}},
        }

    monkeypatch.setattr(copilot_session, "run_browser_selector_swarm", fake_swarm)
    for session_id in ("s1", "s2"):
        task_path = tmp_path / f"{session_id}.md"
        task_path.write_text(
            "Build browser automation\ntarget_url: https://example.test/form\nintent: Submit\n",
            encoding="utf-8",
        )
        start_copilot_session(task_path, root_dir=tmp_path, session_id=session_id)
        answer_copilot_question(session_id, "intake.confirm_scope", "continue", root_dir=tmp_path)
        state = await advance_copilot_session(session_id, root_dir=tmp_path, config=HarnessConfig())

    assert calls["count"] == 1
    assert state["discovery"]["cache"]["status"] == "hit"


@pytest.mark.asyncio
async def test_run_copilot_try_url_creates_task_and_report(tmp_path, monkeypatch):
    import harness.copilot_session as copilot_session
    from harness.copilot_session import run_copilot_try_url

    async def fake_swarm(url, **kwargs):
        return {
            "status": "passed",
            "url": url,
            "summary": {"interactive_elements": 1, "candidates": 1, "validated": 1},
            "artifacts": {"report": "selector_swarm_report.json", "screenshot": "screenshot.png"},
            "validation": {"winner": {"selector": {"strategy": "role", "role": "button", "name": "Submit"}}},
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(copilot_session, "run_browser_selector_swarm", fake_swarm)
    wf_path = tmp_path / "workflow.yaml"
    _noop_workflow(wf_path)

    state = await run_copilot_try_url(
        "https://example.test/form",
        workflow_path=wf_path,
        intent="Submit",
        root_dir=tmp_path,
        session_id="try1",
        config=HarnessConfig(),
    )

    assert state["phase"] == "review"
    assert state["run"]["status"] == "passed"
    assert "target_url: https://example.test/form" in (tmp_path / "builder_sessions" / "try1" / "task.md").read_text()
    assert Path(state["artifacts"]["copilot_report_md"]).exists()
