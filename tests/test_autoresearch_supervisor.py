"""Tests for the autonomous autoresearch supervisor."""

from __future__ import annotations

import json
from pathlib import Path

from tools import autoresearch_supervisor as supervisor
from tools.autoresearch_runner import AutoresearchConfig


def _supervisor_config(tmp_path: Path, agent_command: str = "") -> supervisor.SupervisorConfig:
    return supervisor.SupervisorConfig(
        workdir=tmp_path,
        interval_seconds=1,
        max_cycles=1,
        session_id="test",
        git_binary="git",
        agent_command=agent_command,
        review_command="",
        auto_merge=False,
        push=False,
        memory_url="http://127.0.0.1:1",
        memory_required=False,
        allowed_paths=["tools/", "tests/", ".autoresearch/"],
    )


def _autoresearch_config(tmp_path: Path) -> AutoresearchConfig:
    return AutoresearchConfig(
        workdir=tmp_path,
        session_dir=tmp_path / ".autoresearch",
        metric_name="score",
        allowed_paths=["tools/", "tests/", ".autoresearch/"],
        memory_url="http://127.0.0.1:1",
        memory_required=False,
    )


def _write_session_files(tmp_path: Path) -> None:
    session_dir = tmp_path / ".autoresearch"
    session_dir.mkdir()
    (session_dir / "autoresearch.md").write_text("# Autoresearch\n", encoding="utf-8")
    (session_dir / "autoresearch.sh").write_text(
        "#!/usr/bin/env bash\nprintf 'METRIC score=1\\n'\n",
        encoding="utf-8",
    )
    (session_dir / "autoresearch.checks.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")


def test_load_supervisor_config_reads_repo_defaults(tmp_path):
    config_path = tmp_path / ".autoresearch" / "autoresearch.supervisor.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "interval_seconds": 5,
                "session_id": "nightly",
                "agent_command": "",
                "auto_merge": False,
                "push": False,
                "max_artifact_bytes": 1024,
                "max_recent_rejections": 2,
                "allowed_paths": ["tools/"],
            }
        ),
        encoding="utf-8",
    )

    config = supervisor.load_supervisor_config(str(config_path), tmp_path)

    assert config.interval_seconds == 5
    assert config.branch_name == "autoresearch/nightly"
    assert config.agent_command == ""
    assert config.auto_merge is False
    assert config.max_artifact_bytes == 1024
    assert config.max_recent_rejections == 2
    assert config.allowed_paths == ["tools/"]


def test_discover_improvements_finds_allowed_code_markers(tmp_path):
    path = tmp_path / "tools" / "example.py"
    path.parent.mkdir()
    path.write_text("# TODO: simplify selector scoring\n", encoding="utf-8")
    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)

    candidates = supervisor.discover_improvements(config, autoresearch_config)

    assert candidates[0]["source"] == "code_marker"
    assert candidates[0]["file"] == "tools/example.py"


def test_build_supervisor_prompt_includes_candidates_and_rules(tmp_path):
    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)
    autoresearch_config.session_dir.mkdir()
    autoresearch_config.ideas_path.write_text("- [ ] Tune reports\n", encoding="utf-8")

    prompt = supervisor.build_supervisor_prompt(
        config,
        autoresearch_config,
        [{"source": "test", "title": "Improve reports", "priority": 1}],
    )

    assert "Autonomous supervisor instructions" in prompt
    assert "Improve reports" in prompt
    assert "Do not commit, merge, push" in prompt


def test_integration_gate_blocks_outside_allowed_paths(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(supervisor, "changed_files", lambda *_args: ["main.py"])

    result = supervisor.integration_gate(config, autoresearch_config)

    assert result["status"] == "outside_allowed_paths"
    assert result["files"] == ["main.py"]


def test_integration_gate_blocks_generated_artifacts(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)
    autoresearch_config.allowed_paths.append("reports/")
    monkeypatch.setattr(supervisor, "changed_files", lambda *_args: ["reports/output.html"])

    result = supervisor.integration_gate(config, autoresearch_config)

    assert result["status"] == "generated_artifacts"


def test_secret_scan_files_detects_sensitive_content(tmp_path):
    path = tmp_path / "tools" / "example.py"
    path.parent.mkdir()
    path.write_text("API_KEY='abc123'\n", encoding="utf-8")

    assert supervisor.secret_scan_files(tmp_path, ["tools/example.py"]) == ["tools/example.py"]


def test_confidence_gate_blocks_missing_or_low_confidence(tmp_path):
    config = _supervisor_config(tmp_path)
    config.min_confidence = 2.0

    missing = supervisor.confidence_gate_failure(config, {"confidence": None})
    low = supervisor.confidence_gate_failure(config, {"confidence": 1.5})
    enough = supervisor.confidence_gate_failure(config, {"confidence": 2.5})

    assert missing and missing["status"] == "low_confidence"
    assert low and low["status"] == "low_confidence"
    assert enough is None


def test_build_review_report_extracts_blocking_findings():
    review = supervisor.CommandResult(
        command="review",
        exit_code=0,
        duration_seconds=1.0,
        stdout="::code-comment{title=\"[P1] Bad merge\" body=\"blocks\"}\n",
        stderr="",
    )

    report = supervisor.build_review_report(review)

    assert report["status"] == "blocked"
    assert report["blocking_findings"]


def test_run_review_gate_reads_review_output_file(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.review_command = "review"
    config.worktree_path.mkdir(parents=True)

    def _fake_review(*_args):
        review_path = config.worktree_path / ".autoresearch" / "review.md"
        review_path.parent.mkdir(parents=True)
        review_path.write_text("[P1] Missing rollback protection\n", encoding="utf-8")
        return supervisor.CommandResult("review", 0, 0.0, "", "")

    monkeypatch.setattr(supervisor, "run_prompt_command", _fake_review)

    result = supervisor.run_review_gate(config)

    assert result["status"] == "review_blocked"
    assert result["review"]["blocking_findings"]


def test_run_hook_executes_executable_script(tmp_path):
    config = _supervisor_config(tmp_path)
    hooks = tmp_path / ".autoresearch" / "autoresearch.hooks"
    hooks.mkdir(parents=True)
    hook = hooks / "before.sh"
    hook.write_text("#!/usr/bin/env bash\ncat\n", encoding="utf-8")
    hook.chmod(0o755)

    result = supervisor.run_hook(config, "before", {"candidate": "x"})

    assert result.passed
    assert '"candidate": "x"' in result.stdout


def test_supervisor_heartbeat_includes_extended_checks(tmp_path, monkeypatch):
    class _Check:
        def to_dict(self):
            return {"name": "memory", "status": "ok", "detail": ""}

    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(supervisor, "run_heartbeat", lambda _config: [_Check()])

    checks = supervisor.run_supervisor_heartbeat(config, autoresearch_config)

    names = {check["name"] for check in checks}
    assert {"memory", "disk", "correctness", "evidence", "thrash", "noise"} <= names


def test_remote_freshness_gate_blocks_failed_update(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    monkeypatch.setattr(
        supervisor,
        "update_main_from_remote",
        lambda _config: supervisor.CommandResult("fetch", 1, 0.0, "", "diverged"),
    )

    result = supervisor.remote_freshness_gate(config)

    assert result["status"] == "remote_advanced_or_diverged"


def test_supervisor_cycle_blocks_failed_worktree_update(tmp_path, monkeypatch):
    _write_session_files(tmp_path)
    config = _supervisor_config(tmp_path, agent_command="agent")
    monkeypatch.setattr(
        supervisor,
        "ensure_worktree",
        lambda _config: supervisor.CommandResult("wt", 0, 0.0, "", ""),
    )
    monkeypatch.setattr(supervisor, "sync_autoresearch_files", lambda _config: None)
    monkeypatch.setattr(
        supervisor,
        "update_worktree_from_main",
        lambda _config: supervisor.CommandResult("rebase", 1, 0.0, "", "conflict"),
    )
    monkeypatch.setattr(supervisor, "reset_worktree_and_audit", lambda _c, _a, result: result)

    result = supervisor.run_supervisor_cycle(config)

    assert result["status"] == "worktree_update_failed"


def test_repair_worktree_aborts_rebase_and_resets_to_main(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.worktree_path.mkdir(parents=True)
    calls = []

    def _fake_git(_git_binary, args, _cwd, timeout_seconds=30):
        calls.append(args)
        return supervisor.CommandResult("git", 0, 0.0, "", "")

    monkeypatch.setattr(supervisor, "run_git", _fake_git)

    supervisor.repair_worktree_to_main(config)

    assert ["rebase", "--abort"] in calls
    assert ["merge", "--abort"] in calls
    assert ["reset", "--hard", "main"] in calls
    assert ["clean", "-fd"] in calls


def test_supervisor_cycle_without_agent_writes_plan_and_audit(tmp_path):
    _write_session_files(tmp_path)
    config = _supervisor_config(tmp_path, agent_command="")

    result = supervisor.run_supervisor_cycle(config)

    assert result["status"] == "planned"
    assert (tmp_path / ".autoresearch" / "supervisor_plan.md").exists()
    audit = (tmp_path / ".autoresearch" / "supervisor.jsonl").read_text(encoding="utf-8")
    assert '"status": "planned"' in audit
