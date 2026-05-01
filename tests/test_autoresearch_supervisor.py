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
        scout_enabled=False,
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
                "git_user_name": "bot",
                "git_user_email": "bot@example.test",
                "max_artifact_bytes": 1024,
                "max_recent_rejections": 2,
                "improvement_scouts": {
                    "enabled": True,
                    "max_parallel": 2,
                    "agents": [
                        {
                            "name": "code_explorer",
                            "focus": "Find focused source improvements.",
                            "paths": ["tools/"],
                            "model": "gpt-5.4-mini",
                            "reasoning_effort": "low",
                            "timeout_seconds": 30,
                        }
                    ],
                },
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
    assert config.git_user_name == "bot"
    assert config.git_user_email == "bot@example.test"
    assert config.max_artifact_bytes == 1024
    assert config.max_recent_rejections == 2
    assert config.allowed_paths == ["tools/"]
    assert config.scout_enabled is True
    assert config.scout_max_parallel == 2
    assert config.scout_agents[0].name == "code_explorer"
    assert config.scout_agents[0].reasoning_effort == "low"


def test_load_supervisor_config_replaces_legacy_platform_commands(tmp_path, monkeypatch):
    config_path = tmp_path / ".autoresearch" / "autoresearch.supervisor.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "git_binary": "/Users/rau/bin/codex-git-proxy",
                "agent_command": "/Applications/Codex.app/Contents/Resources/codex exec --full-auto --cd . -",
                "review_command": "/Applications/Codex.app/Contents/Resources/codex exec review --uncommitted --full-auto --output-last-message .autoresearch/review.md",
                "post_merge_command": "bash .autoresearch/autoresearch.checks.sh",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        supervisor,
        "is_legacy_platform_command",
        lambda value: value.startswith("/Users/") or value.startswith("/Applications/"),
    )
    monkeypatch.setattr(
        supervisor,
        "is_legacy_post_merge_command",
        lambda value: value == "bash .autoresearch/autoresearch.checks.sh",
    )
    monkeypatch.setattr(
        supervisor.shutil,
        "which",
        lambda name: {
            "git": "C:\\Program Files\\Git\\cmd\\git.exe",
            "codex": "C:\\Users\\Rau\\AppData\\Roaming\\npm\\codex.CMD",
            "bash": "C:\\Program Files\\Git\\bin\\bash.exe",
        }.get(name),
    )
    monkeypatch.setattr(supervisor, "find_bash", lambda: "C:\\Program Files\\Git\\bin\\bash.exe")

    config = supervisor.load_supervisor_config(str(config_path), tmp_path)

    assert config.git_binary == "C:\\Program Files\\Git\\cmd\\git.exe"
    assert "C:\\Users\\Rau\\AppData\\Roaming\\npm\\codex.CMD" in config.agent_command
    assert " exec " in config.agent_command
    assert " review " in config.review_command
    assert "C:\\Program Files\\Git\\bin\\bash.exe" in config.post_merge_command
    assert ".autoresearch/autoresearch.checks.sh" in config.post_merge_command


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
    assert "Read-only scout subagent results" in prompt
    assert "Do not commit, merge, push" in prompt
    assert supervisor.AGENT_MANIFEST_MARKER in prompt
    manifest_line = prompt.rsplit(supervisor.AGENT_MANIFEST_MARKER, 1)[1].splitlines()[0].strip()
    assert json.loads(manifest_line)["rollback_hint"] == "how to revert safely"


def test_merge_scout_candidates_front_loads_scout_proposals(tmp_path):
    config = _supervisor_config(tmp_path)
    config.scout_enabled = False
    scout_results = [
        {
            "name": "code_explorer",
            "status": "sent",
            "proposed_candidates": [
                {
                    "source": "scout:code_explorer",
                    "priority": 4,
                    "title": "Add missing review guard",
                    "detail": "A narrow guard is missing.",
                }
            ],
        }
    ]

    merged = supervisor.merge_scout_candidates(
        [{"source": "fallback", "priority": 20, "title": "Fallback"}],
        scout_results,
    )

    assert merged[0]["source"] == "scout:code_explorer"


def test_sanitize_scout_candidates_tolerates_non_numeric_priority():
    agent = supervisor.ScoutAgentConfig(name="code_explorer", focus="Find improvements.")

    candidates = supervisor.sanitize_scout_candidates(
        [
            {
                "title": "Tighten parsing",
                "detail": "Scout returned a non-numeric priority.",
                "priority": "high",
            }
        ],
        agent,
    )

    assert candidates[0]["priority"] == 8


def test_run_improvement_scouts_disabled_reports_each_agent(tmp_path):
    config = _supervisor_config(tmp_path)
    config.scout_agents = [
        supervisor.ScoutAgentConfig(name="code_explorer", focus="Find improvements.")
    ]
    autoresearch_config = _autoresearch_config(tmp_path)

    results = supervisor.run_improvement_scouts(config, autoresearch_config, [])

    assert results[0]["name"] == "code_explorer"
    assert results[0]["status"] == "disabled"


def test_audit_progress_writes_live_supervisor_event(tmp_path):
    config = _supervisor_config(tmp_path)

    supervisor.audit_progress(config, "running:scouts", "Running scouts.", {"candidate_count": 2})

    entries = supervisor.read_supervisor_audit(config.audit_path)
    assert entries[0]["type"] == "supervisor_progress"
    assert entries[0]["status"] == "running:scouts"
    assert entries[0]["candidate_count"] == 2


def test_run_improvement_scouts_unavailable_keeps_cycle_deterministic(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.scout_enabled = True
    config.scout_agents = [
        supervisor.ScoutAgentConfig(name="code_explorer", focus="Find improvements.")
    ]
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(supervisor, "find_codex_cli", lambda: None)

    results = supervisor.run_improvement_scouts(config, autoresearch_config, [])

    assert results[0]["status"] == "unavailable"
    assert results[0]["proposed_candidates"] == []


def test_run_improvement_scouts_parses_json_candidates(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.scout_enabled = True
    config.scout_agents = [
        supervisor.ScoutAgentConfig(name="code_explorer", focus="Find improvements.")
    ]
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(supervisor, "find_codex_cli", lambda: "/bin/codex")

    def _fake_call(_codex_path, _workdir, _agent, _prompt):
        return json.dumps(
            {
                "summary": "Found one narrow issue.",
                "candidates": [
                    {
                        "title": "Tighten audit parsing",
                        "detail": "Malformed audit lines should stay ignored.",
                        "files": ["tools/autoresearch_supervisor.py"],
                        "priority": 3,
                        "risk": "low",
                        "verification": "python3 -m pytest tests/test_autoresearch_supervisor.py",
                    }
                ],
                "notes": ["read-only"],
            }
        )

    monkeypatch.setattr(supervisor, "call_codex_scout", _fake_call)

    results = supervisor.run_improvement_scouts(config, autoresearch_config, [])

    assert results[0]["status"] == "sent"
    assert results[0]["proposed_candidates"][0]["source"] == "scout:code_explorer"


def test_parse_agent_change_manifest_reads_last_marker_and_redacts_errors():
    output = """
progress
AHE_CHANGE_MANIFEST: {"hypothesis":"old"}
final
AHE_CHANGE_MANIFEST: {"hypothesis":"agent","failure_evidence":["evidence"],"predicted_fixes":["fix"]}
"""

    parsed = supervisor.parse_agent_change_manifest(output)

    assert parsed["hypothesis"] == "agent"
    assert parsed["predicted_fixes"] == ["fix"]

    invalid = supervisor.parse_agent_change_manifest("AHE_CHANGE_MANIFEST: password=secret")
    assert invalid["manifest_error"] == "agent_manifest_invalid_json"
    assert "secret" not in invalid["raw_preview"]

    not_object = supervisor.parse_agent_change_manifest("AHE_CHANGE_MANIFEST: [1]")
    assert not_object["manifest_error"] == "agent_manifest_not_object"


def test_build_change_manifest_records_predictions_component_and_limits(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(
        supervisor,
        "changed_files",
        lambda *_args: ["tools/autoresearch_runner.py", "tests/test_autoresearch_runner.py"]
        + [f"tools/extra_{index}.py" for index in range(80)],
    )

    manifest = supervisor.build_change_manifest(
        config,
        autoresearch_config,
        [
            {
                "title": "Improve attribution evidence",
                "detail": "Runs need falsifiable predictions.",
            }
        ]
        + [{"title": f"extra {index}", "detail": "extra"} for index in range(20)],
    )

    assert manifest["schema"] == "ahe.change_manifest.v1"
    assert manifest["component_type"] == "test+tooling"
    assert manifest["predicted_fixes"][0] == "Improve attribution evidence"
    assert manifest["failure_evidence"][0] == "Runs need falsifiable predictions."
    assert len(manifest["changed_files"]) == 50
    assert len(manifest["predicted_fixes"]) == 10
    assert len(manifest["failure_evidence"]) == 5
    assert manifest["rollback_hint"]


def test_build_change_manifest_prefers_agent_falsifiable_fields(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(supervisor, "changed_files", lambda *_args: ["harness/ai/agent.py"])

    manifest = supervisor.build_change_manifest(
        config,
        autoresearch_config,
        [{"title": "candidate", "detail": "generic"}],
        agent_manifest={
            "hypothesis": "agent hypothesis",
            "failure_evidence": ["agent evidence"],
            "root_cause": "agent cause",
            "targeted_fix": "agent fix",
            "component_type": "ai",
            "predicted_fixes": ["agent fix prediction"],
            "predicted_regressions": ["agent risk"],
            "rollback_hint": "agent rollback",
        },
    )

    assert manifest["source"] == "autoresearch_supervisor+agent"
    assert manifest["hypothesis"] == "agent hypothesis"
    assert manifest["failure_evidence"] == ["agent evidence"]
    assert manifest["predicted_fixes"] == ["agent fix prediction"]
    assert manifest["predicted_regressions"] == ["agent risk"]
    assert manifest["rollback_hint"] == "agent rollback"
    assert manifest["metadata"]["agent_component_type"] == "ai"


def test_shell_join_quotes_for_windows_and_posix(monkeypatch):
    monkeypatch.setattr(supervisor.os, "name", "nt")
    assert supervisor.shell_join(["C:\\Program Files\\Python\\python.exe", "tools/autoresearch_runner.py"]).startswith('"C:\\Program Files')

    monkeypatch.setattr(supervisor.os, "name", "posix")
    assert supervisor.shell_join(["/usr/bin/python3", "tools/autoresearch_runner.py"]) == "/usr/bin/python3 tools/autoresearch_runner.py"


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


def test_ensure_git_identity_configures_missing_identity(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.worktree_path.mkdir(parents=True)
    config.git_user_name = "bot"
    config.git_user_email = "bot@example.test"
    state: dict[str, str] = {}
    calls = []

    def _fake_output(_git_binary, args, _cwd):
        if args == ["config", "user.name"]:
            return state.get("name", "")
        if args == ["config", "user.email"]:
            return state.get("email", "")
        return ""

    def _fake_git(_git_binary, args, _cwd, timeout_seconds=30):
        calls.append(args)
        if args[:2] == ["config", "user.name"]:
            state["name"] = args[2]
        if args[:2] == ["config", "user.email"]:
            state["email"] = args[2]
        return supervisor.CommandResult("git", 0, 0.0, "", "")

    monkeypatch.setattr(supervisor, "git_output", _fake_output)
    monkeypatch.setattr(supervisor, "run_git", _fake_git)

    result = supervisor.ensure_git_identity(config)

    assert result.passed
    assert ["config", "user.name", "bot"] in calls
    assert ["config", "user.email", "bot@example.test"] in calls


def test_ensure_git_identity_blocks_missing_identity(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.worktree_path.mkdir(parents=True)
    monkeypatch.setattr(supervisor, "git_output", lambda *_args: "")

    result = supervisor.ensure_git_identity(config)

    assert not result.passed
    assert "Missing git user.name or user.email" in result.stderr


def test_supervisor_cycle_passes_change_manifest_to_runner(tmp_path, monkeypatch):
    _write_session_files(tmp_path)
    config = _supervisor_config(tmp_path, agent_command="agent")
    config.worktree_path.mkdir(parents=True)
    captured_env = {}

    monkeypatch.setattr(
        supervisor,
        "discover_improvements",
        lambda *_args: [{"title": "Improve attribution", "detail": "Missing manifest"}],
    )
    monkeypatch.setattr(
        supervisor,
        "ensure_worktree",
        lambda _config: supervisor.CommandResult("wt", 0, 0.0, "", ""),
    )
    monkeypatch.setattr(
        supervisor,
        "update_worktree_from_main",
        lambda _config: supervisor.CommandResult("update", 0, 0.0, "", ""),
    )
    monkeypatch.setattr(supervisor, "sync_autoresearch_files", lambda _config: None)
    agent_output = (
        "No blocking findings.\n"
        + supervisor.AGENT_MANIFEST_MARKER
        + " "
        + json.dumps(
            {
                "hypothesis": "agent says attribution improves",
                "failure_evidence": ["agent saw missing manifest"],
                "root_cause": "agent root cause",
                "targeted_fix": "agent targeted fix",
                "component_type": "tooling",
                "predicted_fixes": ["agent predicted fix"],
                "predicted_regressions": ["agent predicted regression"],
                "rollback_hint": "agent rollback",
            }
        )
    )
    monkeypatch.setattr(
        supervisor,
        "run_prompt_command",
        lambda *_args: supervisor.CommandResult("prompt", 0, 0.0, agent_output, ""),
    )
    monkeypatch.setattr(supervisor, "changed_files", lambda *_args: ["tools/example.py"])

    def _fake_run_command(_command, cwd, _timeout, extra_env=None):
        captured_env.update(extra_env or {})
        log = cwd / ".autoresearch" / "autoresearch.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            json.dumps(
                {
                    "type": "run",
                    "run": 1,
                    "status": "keep",
                    "metric": 2,
                    "metric_name": "score",
                    "lesson": "accepted",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return supervisor.CommandResult("runner", 0, 0.0, "", "")

    monkeypatch.setattr(supervisor, "run_command", _fake_run_command)
    monkeypatch.setattr(
        supervisor,
        "commit_worktree",
        lambda *_args: supervisor.CommandResult("commit", 0, 0.0, "", ""),
    )
    monkeypatch.setattr(supervisor, "git_output", lambda *_args: "abc123")
    monkeypatch.setattr(
        supervisor,
        "tag_winner",
        lambda *_args: supervisor.CommandResult("tag", 0, 0.0, "", ""),
    )
    monkeypatch.setattr(supervisor, "append_learning", lambda *_args: None)

    result = supervisor.run_supervisor_cycle(config)

    assert result["status"] == "committed"
    manifest = json.loads(captured_env[supervisor.CHANGE_MANIFEST_ENV])
    assert manifest["source"] == "autoresearch_supervisor+agent"
    assert manifest["component_type"] == "tooling"
    assert manifest["failure_evidence"] == ["agent saw missing manifest"]
    assert manifest["predicted_fixes"] == ["agent predicted fix"]


def test_supervisor_cycle_without_agent_writes_plan_and_audit(tmp_path):
    _write_session_files(tmp_path)
    config = _supervisor_config(tmp_path, agent_command="")

    result = supervisor.run_supervisor_cycle(config)

    assert result["status"] == "planned"
    assert (tmp_path / ".autoresearch" / "supervisor_plan.md").exists()
    audit = (tmp_path / ".autoresearch" / "supervisor.jsonl").read_text(encoding="utf-8")
    assert '"status": "planned"' in audit

def test_free_mutation_prompt_allows_repository_scope(tmp_path):
    config = _supervisor_config(tmp_path)
    config.autonomy_level = supervisor.AUTONOMY_FREE
    config.mutation_scope = supervisor.MUTATION_SCOPE_REPOSITORY
    config.require_review = False
    autoresearch_config = _autoresearch_config(tmp_path)
    autoresearch_config.session_dir.mkdir()

    prompt = supervisor.build_supervisor_prompt(
        config,
        autoresearch_config,
        [{"source": "test", "title": "Improve main CLI", "priority": 1}],
    )

    assert "Free-mutation mode is active" in prompt
    assert "any repository source" in prompt
    assert "Automated review is disabled" in prompt
    assert '"mutation_scope": "repository"' in prompt


def test_integration_gate_free_scope_allows_main_py_but_blocks_forbidden_paths(tmp_path, monkeypatch):
    config = _supervisor_config(tmp_path)
    config.mutation_scope = supervisor.MUTATION_SCOPE_REPOSITORY
    autoresearch_config = _autoresearch_config(tmp_path)
    monkeypatch.setattr(supervisor, "changed_files", lambda *_args: ["main.py"])

    allowed = supervisor.integration_gate(config, autoresearch_config)

    assert allowed["status"] == "ok"
    assert allowed["mutation_scope"] == supervisor.MUTATION_SCOPE_REPOSITORY

    monkeypatch.setattr(supervisor, "changed_files", lambda *_args: [".env"])
    blocked = supervisor.integration_gate(config, autoresearch_config)

    assert blocked["status"] == "forbidden_mutation_paths"


def test_scan_tech_radar_candidates_reads_recent_backlog(tmp_path):
    path = tmp_path / ".autoresearch" / "tech_radar_candidates.md"
    path.parent.mkdir()
    path.write_text(
        "## now\n"
        "- [ ] Investigate Playwright MCP: new browser tooling (browser-automation; tags: mcp)\n"
        "- [ ] Investigate OpenTelemetry Python: tracing update (observability; tags: traces)\n",
        encoding="utf-8",
    )

    candidates = supervisor.scan_tech_radar_candidates(tmp_path)

    assert candidates[0]["source"] == "tech_radar"
    assert "OpenTelemetry" in candidates[0]["title"]


def test_skipped_review_report_is_machine_readable(tmp_path):
    config = _supervisor_config(tmp_path)
    config.worktree_path.mkdir(parents=True)
    config.autonomy_level = supervisor.AUTONOMY_FREE
    config.mutation_scope = supervisor.MUTATION_SCOPE_REPOSITORY
    config.require_review = False

    result = supervisor.write_skipped_review_report(config)

    assert result["status"] == "ok"
    report_path = config.worktree_path / ".autoresearch" / "review.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "skipped"
    assert report["reason"] == "require_review=false"
