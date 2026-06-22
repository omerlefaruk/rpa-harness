"""File-backed copilot sessions for phase-by-phase automation building."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from harness.autopilot import _policy_violations, load_autopilot_policy
from harness.builder import create_builder_session
from harness.config import HarnessConfig
from harness.core.artifacts import read_json, read_jsonl
from harness.core.ids import safe_session_id
from harness.rpa.yaml_runner import YamlWorkflowRunner, load_workflow_yaml
from harness.security import redact_value, sanitize_url
from harness.selectors.browser_swarm import run_browser_selector_swarm
from harness.verification import validate_workflow_report

WORKFLOW_LINE_RE = re.compile(r"^\s*workflow(?:_path)?:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
TARGET_URL_RE = re.compile(r"^\s*target_url:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
INTENT_RE = re.compile(r"^\s*intent:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
PHASES = ["intake", "policy", "discovery", "draft", "validate", "preflight", "safe_run", "review", "promoted"]


def start_copilot_session(
    task_path: str | Path,
    *,
    root_dir: str | Path = ".",
    session_id: str | None = None,
) -> Path:
    task = Path(task_path)
    root = Path(root_dir)
    session_dir = create_builder_session(task, session_id=session_id, root_dir=root_dir)
    for name in ("questions.jsonl", "answers.jsonl"):
        path = session_dir / name
        if path.exists():
            path.unlink()
    text = task.read_text(encoding="utf-8", errors="replace")
    workflow_path = _resolve_workflow_path(task, text, root)
    target_url = _line_value(TARGET_URL_RE, text, sanitize=True)
    state = {
        "schema_version": 1,
        "session_id": session_dir.name,
        "path": str(session_dir),
        "task_path": str(task.resolve()),
        "task_spec": str(session_dir / "task_spec.md"),
        "status": "waiting",
        "phase": "intake",
        "phases": PHASES,
        "workflow_path": workflow_path,
        "target_url": target_url,
        "intent": _line_value(INTENT_RE, text),
        "discovery": {},
        "validation": {},
        "preflight": {},
        "run": {},
        "artifacts": {},
        "approvals": {},
        "created_at": _now(),
        "updated_at": _now(),
        "next_question": _question(
            "intake.confirm_scope",
            "Confirm the automation scope, target, inputs, risky actions, and success criteria before discovery.",
            details={
                "workflow_path": workflow_path,
                "target_url": target_url,
                "intent": _line_value(INTENT_RE, text),
            },
        ),
    }
    _write_state(session_dir, state)
    _append_jsonl(session_dir / "questions.jsonl", state["next_question"])
    return session_dir


def read_copilot_session(session_id: str, *, root_dir: str | Path = ".") -> dict[str, Any]:
    session_dir = _session_dir(session_id, root_dir)
    state = _read_state(session_dir)
    state["questions"] = read_jsonl(session_dir / "questions.jsonl")
    state["answers"] = read_jsonl(session_dir / "answers.jsonl")
    return _public_state(state)


def list_copilot_sessions(root_dir: str | Path = ".") -> list[dict[str, Any]]:
    base = Path(root_dir) / "builder_sessions"
    if not base.exists():
        return []
    sessions = []
    for state_path in base.glob("*/copilot_state.json"):
        try:
            state = read_copilot_session(state_path.parent.name, root_dir=root_dir)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        sessions.append(
            {
                "session_id": state.get("session_id"),
                "phase": state.get("phase"),
                "status": state.get("status"),
                "updated_at": state.get("updated_at"),
                "next_question": state.get("next_question"),
                "run": state.get("run"),
                "artifacts": state.get("artifacts"),
                "path": state.get("path"),
            }
        )
    return sorted(sessions, key=lambda item: str(item.get("updated_at") or ""), reverse=True)


def answer_copilot_question(
    session_id: str,
    question_id: str,
    answer: str,
    *,
    root_dir: str | Path = ".",
) -> dict[str, Any]:
    session_dir = _session_dir(session_id, root_dir)
    state = _read_state(session_dir)
    question = state.get("next_question") or {}
    if question.get("id") != question_id:
        raise ValueError(f"active question is {question.get('id')!r}, not {question_id!r}")

    answer_record = {
        "question_id": question_id,
        "answer": answer,
        "answered_at": _now(),
    }
    _append_jsonl(session_dir / "answers.jsonl", answer_record)

    if str(answer).strip().lower() in {"stop", "abort", "quit", "no"}:
        state.update({"status": "blocked", "next_question": None, "updated_at": _now()})
        _write_state(session_dir, state)
        return read_copilot_session(session_id, root_dir=root_dir)

    approvals = dict(state.get("approvals") or {})
    if question_id == "intake.confirm_scope":
        if not _set_policy_question_if_needed(session_dir, state, policy_path=Path(".agents/config/autopilot.yaml")):
            state.update({"phase": "discovery", "status": "ready", "next_question": None})
    elif question_id == "policy.review":
        approvals[question_id] = {
            "answer": answer,
            "approved_at": _now(),
            "details": question.get("details") or {},
            "target_url": state.get("target_url"),
            "workflow_hash": _file_hash(state.get("workflow_path")),
        }
        next_phase = "discovery" if state.get("phase") == "policy" else "preflight"
        state.update({"phase": next_phase, "status": "ready", "next_question": None, "approvals": approvals})
    elif question_id == "review.promote":
        state.update({"phase": "promoted", "status": "completed", "next_question": None})
    else:
        state.update({"status": "ready", "next_question": None})
    state["updated_at"] = _now()
    _write_state(session_dir, state)
    return read_copilot_session(session_id, root_dir=root_dir)


async def advance_copilot_session(
    session_id: str,
    *,
    root_dir: str | Path = ".",
    config: HarnessConfig | None = None,
    policy_path: str | Path = ".agents/config/autopilot.yaml",
) -> dict[str, Any]:
    session_dir = _session_dir(session_id, root_dir)
    state = _read_state(session_dir)
    if state.get("status") == "waiting":
        return read_copilot_session(session_id, root_dir=root_dir)

    phase = state.get("phase")
    if phase == "discovery":
        await _advance_discovery(session_dir, state, config or HarnessConfig.from_env())
    elif phase == "draft":
        _advance_draft(session_dir, state)
    elif phase == "validate":
        _advance_validate(session_dir, state, policy_path)
    elif phase == "preflight":
        await _advance_preflight(session_dir, state, config or HarnessConfig.from_env(), policy_path)
    elif phase == "safe_run":
        await _advance_safe_run(session_dir, state, config or HarnessConfig.from_env())
    elif phase in {"review", "promoted"}:
        if not state.get("next_question") and phase == "review":
            _set_question(
                session_dir,
                state,
                "review.promote",
                "Review the run evidence and promote this automation when it is ready.",
                choices=["promote", "continue", "stop"],
                details={"run": state.get("run"), "artifacts": state.get("artifacts")},
            )
    else:
        _set_question(session_dir, state, "session.unknown_phase", f"Unknown copilot phase: {phase}")

    return read_copilot_session(session_id, root_dir=root_dir)


async def run_copilot_auto(
    task_or_session: str | Path,
    *,
    root_dir: str | Path = ".",
    session_id: str | None = None,
    config: HarnessConfig | None = None,
    policy_path: str | Path = ".agents/config/autopilot.yaml",
    max_turns: int = 20,
) -> dict[str, Any]:
    """Start or continue a copilot session until it needs user review/input."""
    source = Path(task_or_session)
    if source.exists():
        session_dir = start_copilot_session(source, root_dir=root_dir, session_id=session_id)
        active_session_id = session_dir.name
    else:
        active_session_id = safe_session_id(session_id or str(task_or_session))

    log: list[dict[str, Any]] = []
    for _ in range(max_turns):
        state = read_copilot_session(active_session_id, root_dir=root_dir)
        log.append(_auto_log_entry(state))
        question = state.get("next_question") or {}
        if state.get("status") == "waiting" and question.get("id") == "intake.confirm_scope":
            answer_copilot_question(
                active_session_id,
                "intake.confirm_scope",
                "continue",
                root_dir=root_dir,
            )
            continue
        if state.get("status") != "ready":
            state["auto"] = {"status": "stopped", "turns": log}
            return state
        await advance_copilot_session(
            active_session_id,
            root_dir=root_dir,
            config=config,
            policy_path=policy_path,
        )

    state = read_copilot_session(active_session_id, root_dir=root_dir)
    state["auto"] = {"status": "max_turns_reached", "turns": log}
    return state


async def run_copilot_try_url(
    url: str,
    *,
    workflow_path: str | Path | None = None,
    intent: str | None = None,
    root_dir: str | Path = ".",
    session_id: str | None = None,
    config: HarnessConfig | None = None,
    policy_path: str | Path = ".agents/config/autopilot.yaml",
) -> dict[str, Any]:
    root = Path(root_dir)
    safe_id = safe_session_id(session_id or f"try_{_url_slug(url)}_{_short_hash(url)}")
    task_dir = root / "builder_sessions" / safe_id
    task_dir.mkdir(parents=True, exist_ok=True)
    workflow = workflow_path or _known_workflow_for_url(url, root)
    lines = ["Try this automation target.", f"target_url: {sanitize_url(url)}"]
    if intent:
        lines.append(f"intent: {intent}")
    if workflow:
        lines.append(f"workflow: {workflow}")
    (task_dir / "task.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return await run_copilot_auto(
        task_dir / "task.md",
        root_dir=root,
        session_id=safe_id,
        config=config,
        policy_path=policy_path,
    )


async def _advance_discovery(session_dir: Path, state: dict[str, Any], config: HarnessConfig) -> None:
    target_url = state.get("target_url")
    if not target_url:
        state["discovery"] = {"status": "skipped", "reason": "No target_url provided."}
        _set_ready(session_dir, state, "draft")
        return

    output_dir = session_dir / "discovery"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _discovery_cache_path(session_dir, str(target_url), state.get("intent"))
    cached = _read_discovery_cache(cache_path)
    if cached:
        (output_dir / "browser_selector_swarm.json").write_text(
            json.dumps(redact_value(cached["result"]), indent=2, default=str),
            encoding="utf-8",
            newline="\n",
        )
        state["discovery"] = {
            "browser_selector_swarm": cached["summary"],
            "cache": {"status": "hit", "path": str(cache_path)},
        }
        _set_ready(session_dir, state, "draft")
        return

    result = await run_browser_selector_swarm(
        str(target_url),
        output_dir=str(output_dir),
        browser_name=config.browser,
        headless=config.headless,
        wait_until="domcontentloaded",
        intent=state.get("intent"),
        safe_click=False,
        save_raw_html=False,
    )
    summary = {
        "status": result.get("status"),
        "url": result.get("url"),
        "summary": result.get("summary"),
        "artifacts": result.get("artifacts"),
        "winner": (result.get("validation") or {}).get("winner"),
    }
    (output_dir / "browser_selector_swarm.json").write_text(
        json.dumps(redact_value(result), indent=2, default=str),
        encoding="utf-8",
        newline="\n",
    )
    _write_discovery_cache(cache_path, result, summary)
    state["discovery"] = {
        "browser_selector_swarm": redact_value(summary),
        "cache": {"status": "miss", "path": str(cache_path)},
    }
    _set_ready(session_dir, state, "draft")


def _advance_draft(session_dir: Path, state: dict[str, Any]) -> None:
    if not state.get("workflow_path"):
        _set_question(
            session_dir,
            state,
            "draft.workflow_missing",
            "No workflow path is available yet. Add a workflow YAML path to the task or create the draft workflow first.",
            details={"expected_line": "workflow: path/to/workflow.yaml"},
        )
        return
    _set_ready(session_dir, state, "validate")


def _advance_validate(session_dir: Path, state: dict[str, Any], policy_path: str | Path) -> None:
    workflow_path = state.get("workflow_path")
    workflow_hash = _file_hash(workflow_path)
    cached = state.get("validation") or {}
    if cached.get("status") == "passed" and cached.get("workflow_hash") == workflow_hash:
        try:
            workflow = load_workflow_yaml(workflow_path)
        except Exception:
            workflow = {}
        policy = load_autopilot_policy(policy_path)
        violations = _policy_violations(workflow, policy) if workflow else []
        if violations and not _policy_approved(state):
            _set_policy_question(session_dir, state, violations)
            return
        _set_ready(session_dir, state, "preflight")
        return

    try:
        workflow = load_workflow_yaml(workflow_path)
    except Exception as exc:
        _set_question(
            session_dir,
            state,
            "validate.load_failed",
            "The workflow YAML could not be loaded. Fix the file and continue.",
            details={"error": str(exc), "workflow_path": workflow_path},
        )
        return

    validation = validate_workflow_report(workflow)
    state["validation"] = redact_value({
        **validation,
        "status": "failed" if validation["errors"] else "passed",
        "tier": "fast",
        "workflow_hash": workflow_hash,
    })
    if validation["errors"]:
        _set_question(
            session_dir,
            state,
            "validate.fix_errors",
            "Workflow validation failed. Fix the listed errors, then continue.",
            details={"errors": validation["errors"], "warnings": validation.get("warnings", [])},
        )
        return

    policy = load_autopilot_policy(policy_path)
    violations = _policy_violations(workflow, policy)
    if violations and not _policy_approved(state):
        _set_policy_question(session_dir, state, violations)
        return
    _set_ready(session_dir, state, "preflight")


async def _advance_preflight(
    session_dir: Path,
    state: dict[str, Any],
    config: HarnessConfig,
    policy_path: str | Path,
) -> None:
    policy_endpoint = (load_autopilot_policy(policy_path).get("autopilot") or {}).get("browser_cdp_endpoint")
    if policy_endpoint and not config.browser_cdp_endpoint:
        config.browser_cdp_endpoint = policy_endpoint
    result = await YamlWorkflowRunner(config).preflight(str(state.get("workflow_path")))
    state["preflight"] = redact_value(result)
    if result.get("status") != "passed":
        _set_question(
            session_dir,
            state,
            "preflight.resolve_blockers",
            "Preflight found blockers. Resolve them, then continue.",
            details={"preflight": result.get("preflight"), "run_dir": result.get("run_dir")},
        )
        return
    _set_ready(session_dir, state, "safe_run")


async def _advance_safe_run(session_dir: Path, state: dict[str, Any], config: HarnessConfig) -> None:
    result = await YamlWorkflowRunner(config).run(str(state.get("workflow_path")))
    report = str(Path(result["run_dir"]) / "report.html") if result.get("run_dir") else None
    state["run"] = redact_value({**result, "report": report})
    state["artifacts"] = redact_value({"run_dir": result.get("run_dir"), "report": report})
    _set_question(
        session_dir,
        state,
        "review.promote",
        "Review the run evidence and promote this automation when it is ready.",
        choices=["promote", "continue", "stop"],
        details={"status": result.get("status"), "run_dir": result.get("run_dir"), "report": report},
        phase="review",
    )
    state["artifacts"].update(_write_copilot_report(session_dir, state))
    _write_state(session_dir, state)


def _set_policy_question_if_needed(session_dir: Path, state: dict[str, Any], *, policy_path: str | Path) -> bool:
    workflow_path = state.get("workflow_path")
    if not workflow_path:
        return False
    try:
        workflow = load_workflow_yaml(workflow_path)
    except Exception:
        return False
    violations = _policy_violations(workflow, load_autopilot_policy(policy_path))
    if not violations:
        return False
    _set_policy_question(session_dir, state, violations, phase="policy")
    return True


def _set_policy_question(
    session_dir: Path,
    state: dict[str, Any],
    violations: list[dict[str, Any]],
    *,
    phase: str | None = None,
) -> None:
    _set_question(
        session_dir,
        state,
        "policy.review",
        "This workflow includes actions blocked by the automatic policy. Review and explicitly approve before execution.",
        choices=["continue", "stop"],
        details={
            "violations": violations,
            "approval_scope": "current workflow hash and target only",
            "target_url": state.get("target_url"),
            "workflow_hash": _file_hash(state.get("workflow_path")),
        },
        phase=phase,
    )


def _policy_approved(state: dict[str, Any]) -> bool:
    approval = (state.get("approvals") or {}).get("policy.review")
    if not isinstance(approval, dict):
        return False
    return (
        approval.get("target_url") == state.get("target_url")
        and approval.get("workflow_hash") == _file_hash(state.get("workflow_path"))
    )


def _write_copilot_report(session_dir: Path, state: dict[str, Any]) -> dict[str, str]:
    payload = redact_value({
        "schema_version": 1,
        "session_id": state.get("session_id"),
        "status": state.get("status"),
        "phase": state.get("phase"),
        "target_url": state.get("target_url"),
        "workflow_path": state.get("workflow_path"),
        "approvals": state.get("approvals") or {},
        "discovery": state.get("discovery") or {},
        "validation": state.get("validation") or {},
        "preflight": state.get("preflight") or {},
        "run": state.get("run") or {},
        "artifacts": state.get("artifacts") or {},
        "next_question": state.get("next_question"),
        "updated_at": _now(),
    })
    json_path = session_dir / "copilot_report.json"
    md_path = session_dir / "copilot_report.md"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8", newline="\n")
    md_path.write_text(_copilot_report_md(payload), encoding="utf-8", newline="\n")
    return {"copilot_report_json": str(json_path), "copilot_report_md": str(md_path)}


def _copilot_report_md(payload: dict[str, Any]) -> str:
    run = payload.get("run") or {}
    validation = payload.get("validation") or {}
    discovery = payload.get("discovery") or {}
    cache = discovery.get("cache") or {}
    artifacts = payload.get("artifacts") or {}
    return "\n".join(
        [
            f"# Copilot Report: {payload.get('session_id')}",
            "",
            f"- status: {payload.get('status')}",
            f"- phase: {payload.get('phase')}",
            f"- target_url: {payload.get('target_url') or '-'}",
            f"- workflow_path: {payload.get('workflow_path') or '-'}",
            f"- discovery_cache: {cache.get('status') or '-'}",
            f"- validation: {validation.get('status') or '-'}",
            f"- preflight: {(payload.get('preflight') or {}).get('status') or '-'}",
            f"- run_status: {run.get('status') or '-'}",
            f"- run_id: {run.get('run_id') or '-'}",
            f"- report: {artifacts.get('report') or run.get('report') or '-'}",
            "",
            "## Next Question",
            "",
            json.dumps(payload.get("next_question") or {}, indent=2, default=str),
            "",
        ]
    )


def _session_dir(session_id: str, root_dir: str | Path) -> Path:
    session_dir = Path(root_dir) / "builder_sessions" / safe_session_id(session_id)
    if not session_dir.exists():
        raise FileNotFoundError(f"Copilot session not found: {session_id}")
    return session_dir.resolve()


def _read_state(session_dir: Path) -> dict[str, Any]:
    path = session_dir / "copilot_state.json"
    if not path.exists():
        raise FileNotFoundError(f"Copilot state not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _discovery_cache_path(session_dir: Path, target_url: str, intent: str | None) -> Path:
    root = session_dir.parent.parent
    key = _short_hash(json.dumps({"url": target_url, "intent": intent or ""}, sort_keys=True))
    return root / "builder_sessions" / "_cache" / "discovery" / f"{key}.json"


def _read_discovery_cache(path: Path) -> dict[str, Any] | None:
    payload = read_json(path)
    if not payload:
        return None
    if payload.get("summary", {}).get("status") != "passed":
        return None
    return payload


def _write_discovery_cache(path: Path, result: dict[str, Any], summary: dict[str, Any]) -> None:
    if summary.get("status") != "passed":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            redact_value({"schema_version": 1, "created_at": _now(), "summary": summary, "result": result}),
            indent=2,
            default=str,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _file_hash(path: str | Path | None) -> str | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    return sha256(target.read_bytes()).hexdigest()


def _known_workflow_for_url(url: str, root_dir: Path) -> str | None:
    host = urlparse(url).netloc.lower()
    if host.endswith("rpachallenge.com"):
        path = root_dir / "workflows" / "rpa_challenge" / "main.yaml"
        if path.exists():
            return str(path)
    return None


def _url_slug(url: str) -> str:
    parsed = urlparse(url)
    text = parsed.netloc or parsed.path or "url"
    return safe_session_id(text.strip("/")[:40] or "url")


def _short_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _write_state(session_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    (session_dir / "copilot_state.json").write_text(
        json.dumps(_public_state(state), indent=2, default=str),
        encoding="utf-8",
        newline="\n",
    )


def _set_ready(session_dir: Path, state: dict[str, Any], phase: str) -> None:
    state.update({"phase": phase, "status": "ready", "next_question": None})
    _write_state(session_dir, state)


def _set_question(
    session_dir: Path,
    state: dict[str, Any],
    question_id: str,
    question: str,
    *,
    choices: list[str] | None = None,
    details: dict[str, Any] | None = None,
    phase: str | None = None,
) -> None:
    if phase:
        state["phase"] = phase
    state["status"] = "waiting"
    state["next_question"] = _question(question_id, question, choices=choices, details=details)
    _write_state(session_dir, state)
    _append_jsonl(session_dir / "questions.jsonl", state["next_question"])


def _question(
    question_id: str,
    question: str,
    *,
    choices: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    choices = choices or ["continue", "stop"]
    return {
        "id": question_id,
        "question": question,
        "choices": choices,
        "default": choices[0],
        "details": redact_value(details or {}),
        "created_at": _now(),
    }


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(redact_value(payload), default=str) + "\n")


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    public = redact_value(state)
    for key in ("session_id", "path", "task_path", "task_spec"):
        if key in state:
            public[key] = state[key]
    return public


def _auto_log_entry(state: dict[str, Any]) -> dict[str, Any]:
    question = state.get("next_question") or {}
    return {
        "phase": state.get("phase"),
        "status": state.get("status"),
        "question_id": question.get("id"),
    }


def _resolve_workflow_path(task: Path, text: str, root_dir: Path) -> str | None:
    match = WORKFLOW_LINE_RE.search(text)
    if not match:
        return None
    path = Path(match.group(1).strip().strip('"'))
    if path.is_absolute():
        return str(path)
    task_relative = (task.parent / path).resolve()
    if task_relative.exists():
        return str(task_relative)
    return str((root_dir / path).resolve())


def _line_value(pattern: re.Pattern[str], text: str, *, sanitize: bool = False) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip().strip('"')
    return sanitize_url(value) if sanitize else value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
