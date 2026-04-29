#!/usr/bin/env python3
"""
Autonomous supervisor for RPA Harness autoresearch.

This layer owns scheduling, codebase scanning, isolated worktrees, Codex-driven
experiments, review gates, commit, merge, push, and audit logging. The existing
autoresearch runner remains the deterministic measurement judge.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.security import redact_value  # noqa: E402
from tools.autoresearch_runner import (  # noqa: E402
    AutoresearchConfig,
    CommandResult,
    build_codex_prompt,
    load_config,
    read_jsonl,
    run_command,
    run_heartbeat,
    save_to_memory,
)  # noqa: E402

DEFAULT_CODEX = "/Applications/Codex.app/Contents/Resources/codex"
DEFAULT_GIT = "/Users/rau/bin/codex-git-proxy"
DEFAULT_SUPERVISOR_CONFIG = ".autoresearch/autoresearch.supervisor.json"
DEFAULT_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
GENERATED_PATH_PREFIXES = (
    "reports/",
    "runs/",
    "screenshots/",
    "downloads/",
    "logs/",
    "data/",
)
SECRET_PATTERNS = ("api_key", "apikey", "password=", "bearer ", "authorization:")
BLOCKING_REVIEW_MARKERS = ("priority=0", "priority=1", "[p0]", "[p1]")
SUCCESS_STATUSES = {"planned", "committed", "merged", "pushed"}


@dataclass
class SupervisorConfig:
    workdir: Path
    autoresearch_config_path: Path | None = None
    interval_seconds: int = 3600
    max_cycles: int | None = None
    session_id: str = "continuous"
    base_branch: str = "main"
    branch_prefix: str = "autoresearch"
    worktree_root: Path | None = None
    git_binary: str = DEFAULT_GIT
    agent_command: str = (
        f"{shlex.quote(DEFAULT_CODEX)} exec --full-auto --cd . -"
    )
    review_command: str = (
        f"{shlex.quote(DEFAULT_CODEX)} exec review --uncommitted "
        "--full-auto --output-last-message .autoresearch/review.md"
    )
    post_merge_command: str = "bash .autoresearch/autoresearch.checks.sh"
    auto_merge: bool = True
    push: bool = True
    memory_url: str = "http://127.0.0.1:37777"
    memory_required: bool = False
    min_confidence: float | None = None
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES
    max_recent_rejections: int = 3
    allowed_paths: list[str] = field(default_factory=list)

    @property
    def session_dir(self) -> Path:
        return self.workdir / ".autoresearch"

    @property
    def audit_path(self) -> Path:
        return self.session_dir / "supervisor.jsonl"

    @property
    def plan_path(self) -> Path:
        return self.session_dir / "supervisor_plan.md"

    @property
    def review_json_path(self) -> Path:
        return self.session_dir / "review.json"

    @property
    def review_markdown_path(self) -> Path:
        return self.session_dir / "review.md"

    @property
    def learnings_path(self) -> Path:
        return self.session_dir / "autoresearch.learnings.md"

    @property
    def hooks_dir(self) -> Path:
        return self.session_dir / "autoresearch.hooks"

    @property
    def branch_name(self) -> str:
        return f"{self.branch_prefix}/{self.session_id}"

    @property
    def worktree_path(self) -> Path:
        root = self.worktree_root or (self.workdir / ".autoresearch" / "worktrees")
        return root / self.session_id


def main() -> int:
    args = parse_args()
    config = load_supervisor_config(args.config, Path(args.workdir).resolve())

    if args.plan_only:
        autoresearch_config = load_config_for_supervisor(config)
        candidates = discover_improvements(config, autoresearch_config)
        prompt = build_supervisor_prompt(config, autoresearch_config, candidates)
        config.plan_path.write_text(prompt, encoding="utf-8")
        print(config.plan_path)
        return 0

    if args.once:
        result = run_supervisor_cycle(config)
        print(json.dumps(redact_value(result), indent=2))
        return 0 if result.get("status") in SUCCESS_STATUSES else 1

    if args.daemon:
        return run_daemon(config)

    print("Nothing to do. Use --plan-only, --once, or --daemon.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the autoresearch supervisor")
    parser.add_argument("--config", default=None, help="Optional supervisor config JSON")
    parser.add_argument("--workdir", default=".", help="Repository working directory")
    parser.add_argument("--plan-only", action="store_true", help="Scan and write the next plan")
    parser.add_argument("--once", action="store_true", help="Run one supervised cycle")
    parser.add_argument("--daemon", action="store_true", help="Run periodic cycles forever")
    return parser.parse_args()


def load_supervisor_config(config_path: str | None, workdir: Path) -> SupervisorConfig:
    path = Path(config_path) if config_path else workdir / DEFAULT_SUPERVISOR_CONFIG
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

    configured_workdir = Path(data.get("workdir", workdir))
    if not configured_workdir.is_absolute():
        configured_workdir = (workdir / configured_workdir).resolve()

    autoresearch_config_path = data.get("autoresearch_config_path")
    if autoresearch_config_path:
        resolved_config_path = Path(autoresearch_config_path)
        if not resolved_config_path.is_absolute():
            resolved_config_path = (configured_workdir / resolved_config_path).resolve()
    else:
        resolved_config_path = None

    worktree_root = data.get("worktree_root")
    resolved_worktree_root = Path(worktree_root) if worktree_root else None
    if resolved_worktree_root and not resolved_worktree_root.is_absolute():
        resolved_worktree_root = (configured_workdir / resolved_worktree_root).resolve()

    return SupervisorConfig(
        workdir=configured_workdir,
        autoresearch_config_path=resolved_config_path,
        interval_seconds=int(data.get("interval_seconds", 3600)),
        max_cycles=data.get("max_cycles"),
        session_id=data.get("session_id", "continuous"),
        base_branch=data.get("base_branch", "main"),
        branch_prefix=data.get("branch_prefix", "autoresearch"),
        worktree_root=resolved_worktree_root,
        git_binary=data.get("git_binary", DEFAULT_GIT),
        agent_command=data.get(
            "agent_command",
            os.getenv(
                "AUTORESEARCH_AGENT_COMMAND",
                f"{shlex.quote(DEFAULT_CODEX)} exec --full-auto --cd . -",
            ),
        ),
        review_command=data.get(
            "review_command",
            os.getenv(
                "AUTORESEARCH_REVIEW_COMMAND",
                f"{shlex.quote(DEFAULT_CODEX)} exec review --uncommitted "
                "--full-auto --output-last-message .autoresearch/review.md",
            ),
        ),
        post_merge_command=data.get(
            "post_merge_command",
            "bash .autoresearch/autoresearch.checks.sh",
        ),
        auto_merge=bool(data.get("auto_merge", True)),
        push=bool(data.get("push", True)),
        memory_url=data.get("memory_url", "http://127.0.0.1:37777"),
        memory_required=bool(data.get("memory_required", False)),
        min_confidence=data.get("min_confidence"),
        max_artifact_bytes=int(data.get("max_artifact_bytes", DEFAULT_MAX_ARTIFACT_BYTES)),
        max_recent_rejections=int(data.get("max_recent_rejections", 3)),
        allowed_paths=list(data.get("allowed_paths", [])),
    )


def load_config_for_supervisor(config: SupervisorConfig) -> AutoresearchConfig:
    path = str(config.autoresearch_config_path) if config.autoresearch_config_path else None
    autoresearch_config = load_config(path, config.workdir)
    if config.allowed_paths:
        autoresearch_config.allowed_paths = config.allowed_paths
    return autoresearch_config


def run_daemon(config: SupervisorConfig) -> int:
    cycles = 0
    while config.max_cycles is None or cycles < config.max_cycles:
        result = run_supervisor_cycle(config)
        print(json.dumps(redact_value(result), sort_keys=True))
        cycles += 1
        time.sleep(config.interval_seconds)
    return 0


def run_supervisor_cycle(config: SupervisorConfig) -> dict[str, Any]:
    autoresearch_config = load_config_for_supervisor(config)
    heartbeat = run_supervisor_heartbeat(config, autoresearch_config)
    hard_failures = [check for check in heartbeat if check["status"] == "fail"]
    if hard_failures:
        return audit_and_return(
            config,
            autoresearch_config,
            {"status": "heartbeat_failed", "heartbeat": hard_failures},
        )

    candidates = discover_improvements(config, autoresearch_config)
    prompt = build_supervisor_prompt(config, autoresearch_config, candidates)
    before_hook = run_hook(config, "before", {"candidates": candidates})
    if before_hook.passed and before_hook.stdout.strip():
        prompt += "\n\nBefore hook context:\n" + before_hook.stdout[-4000:]
    config.session_dir.mkdir(parents=True, exist_ok=True)
    config.plan_path.write_text(prompt, encoding="utf-8")

    if not config.agent_command.strip():
        return audit_and_return(
            config,
            autoresearch_config,
            {"status": "planned", "plan": str(config.plan_path), "candidates": candidates},
        )

    worktree_result = ensure_worktree(config)
    if not worktree_result.passed:
        return audit_and_return(
            config,
            autoresearch_config,
            {"status": "worktree_failed", "worktree": command_summary(worktree_result)},
        )

    update_result = update_worktree_from_main(config)
    if not update_result.passed:
        return reset_worktree_and_audit(
            config,
            autoresearch_config,
            {"status": "worktree_update_failed", "update": command_summary(update_result)},
        )

    sync_autoresearch_files(config)
    agent_result = run_prompt_command(config.agent_command, config.worktree_path, prompt, 1800)
    if not agent_result.passed:
        return reset_worktree_and_audit(
            config,
            autoresearch_config,
            {"status": "agent_failed", "agent": command_summary(agent_result)},
        )

    experiment_result = run_command(
        f"{shlex.quote(sys.executable)} tools/autoresearch_runner.py --once",
        config.worktree_path,
        1800,
    )
    latest_entry = latest_run_entry(config.worktree_path / ".autoresearch" / "autoresearch.jsonl")
    if not experiment_result.passed or latest_entry.get("status") != "keep":
        return reset_worktree_and_audit(
            config,
            autoresearch_config,
            {
                "status": "experiment_rejected",
                "experiment": command_summary(experiment_result),
                "latest": latest_entry,
            },
        )

    confidence_failure = confidence_gate_failure(config, latest_entry)
    if confidence_failure:
        return reset_worktree_and_audit(
            config,
            autoresearch_config,
            confidence_failure,
        )

    gate = integration_gate(config, autoresearch_config)
    if gate["status"] != "ok":
        return reset_worktree_and_audit(config, autoresearch_config, gate)

    review = run_review_gate(config)
    if review["status"] != "ok":
        return reset_worktree_and_audit(config, autoresearch_config, review)

    commit_result = commit_worktree(config, latest_entry)
    if not commit_result.passed:
        return reset_worktree_and_audit(
            config,
            autoresearch_config,
            {"status": "commit_failed", "commit": command_summary(commit_result)},
        )

    commit_sha = git_output(
        config.git_binary,
        ["rev-parse", "--short=12", "HEAD"],
        config.worktree_path,
    )
    tag_result = tag_winner(config, commit_sha, latest_entry)
    append_learning(config, latest_entry, commit_sha)
    if not config.auto_merge:
        return audit_and_return(
            config,
            autoresearch_config,
            {
                "status": "committed",
                "commit": commit_sha,
                "tag": command_summary(tag_result),
                "latest": latest_entry,
            },
        )

    pre_merge_sha = git_output(config.git_binary, ["rev-parse", config.base_branch], config.workdir)
    merge_result = merge_to_main(config)
    if not merge_result.passed:
        return audit_and_return(
            config,
            autoresearch_config,
            {
                "status": "merge_failed",
                "merge": command_summary(merge_result),
                "commit": commit_sha,
            },
        )

    post_merge = run_command(config.post_merge_command, config.workdir, 900)
    if not post_merge.passed:
        rollback = rollback_main_merge(config, pre_merge_sha)
        return audit_and_return(
            config,
            autoresearch_config,
            {
                "status": "post_merge_failed",
                "post_merge": command_summary(post_merge),
                "rollback": command_summary(rollback),
                "commit": commit_sha,
            },
        )

    if not config.push:
        return audit_and_return(
            config,
            autoresearch_config,
            {
                "status": "merged",
                "commit": commit_sha,
                "tag": command_summary(tag_result),
                "latest": latest_entry,
            },
        )

    remote_gate = remote_freshness_gate(config)
    if remote_gate["status"] != "ok":
        return audit_and_return(
            config,
            autoresearch_config,
            {
                "status": "remote_not_fresh",
                "remote": remote_gate,
                "commit": commit_sha,
            },
        )

    push_result = run_git(config.git_binary, ["push", "origin", config.base_branch], config.workdir)
    return audit_and_return(
        config,
        autoresearch_config,
        {
            "status": "pushed" if push_result.passed else "push_failed",
            "push": command_summary(push_result),
            "commit": commit_sha,
            "tag": command_summary(tag_result),
            "latest": latest_entry,
        },
    )


def run_supervisor_heartbeat(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
) -> list[dict[str, Any]]:
    checks = [check.to_dict() for check in run_heartbeat(autoresearch_config)]
    checks.extend(
        [
            heartbeat_artifact_disk(config),
            heartbeat_last_kept_correctness(autoresearch_config),
            heartbeat_failure_evidence(config),
            heartbeat_thrash(config),
            heartbeat_noise(config, autoresearch_config),
        ]
    )
    return checks


def heartbeat_artifact_disk(config: SupervisorConfig) -> dict[str, Any]:
    total = 0
    for rel in ("reports", "runs", "screenshots", "downloads", "logs", ".autoresearch"):
        root = config.workdir / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    if total > config.max_artifact_bytes:
        return {
            "name": "disk",
            "status": "fail",
            "detail": f"Artifact bytes {total} exceed {config.max_artifact_bytes}",
        }
    return {"name": "disk", "status": "ok", "detail": str(total)}


def heartbeat_last_kept_correctness(config: AutoresearchConfig) -> dict[str, Any]:
    kept = [entry for entry in read_jsonl(config.jsonl_path) if entry.get("status") == "keep"]
    if not kept:
        return {"name": "correctness", "status": "warn", "detail": "No kept run yet"}
    checks = kept[-1].get("checks") or {}
    if checks.get("exit_code") not in {0, None}:
        return {
            "name": "correctness",
            "status": "fail",
            "detail": "Last kept run does not have passing checks",
        }
    return {"name": "correctness", "status": "ok", "detail": f"run {kept[-1].get('run')}"}


def heartbeat_failure_evidence(config: SupervisorConfig) -> dict[str, Any]:
    required = {"workflow_id", "run_id", "status", "failed_step_id", "action_type", "error_message"}
    reports = sorted((config.workdir / "runs").glob("**/failure_report.json"), reverse=True)[:5]
    missing: list[str] = []
    for path in reports:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing.append(path.name)
            continue
        absent = sorted(required - payload.keys())
        if absent:
            missing.append(f"{path.parent.name}:{','.join(absent)}")
    if missing:
        return {"name": "evidence", "status": "warn", "detail": "; ".join(missing[:3])}
    return {"name": "evidence", "status": "ok", "detail": f"{len(reports)} report(s)"}


def heartbeat_thrash(config: SupervisorConfig) -> dict[str, Any]:
    entries = read_supervisor_audit(config.audit_path)[-config.max_recent_rejections:]
    rejected = {
        "experiment_rejected",
        "agent_failed",
        "review_failed",
        "review_blocked",
        "low_confidence",
        "checks_failed",
    }
    if len(entries) >= config.max_recent_rejections and all(
        entry.get("status") in rejected for entry in entries
    ):
        return {
            "name": "thrash",
            "status": "warn",
            "detail": f"{len(entries)} recent rejected cycles",
        }
    return {"name": "thrash", "status": "ok", "detail": ""}


def heartbeat_noise(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
) -> dict[str, Any]:
    if config.min_confidence is None:
        return {"name": "noise", "status": "ok", "detail": "confidence gate disabled"}
    best = latest_run_entry(autoresearch_config.jsonl_path)
    failure = confidence_gate_failure(config, best)
    if failure:
        return {"name": "noise", "status": "warn", "detail": json.dumps(failure)}
    return {"name": "noise", "status": "ok", "detail": ""}


def discover_improvements(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidates.extend(scan_code_markers(config.workdir, autoresearch_config.allowed_paths))
    candidates.extend(scan_recent_failures(config.workdir))
    candidates.extend(
        search_memory(
            config.memory_url,
            "rpa-harness improvement failures autoresearch",
            limit=5,
        )
    )

    if not candidates:
        candidates.append(
            {
                "source": "fallback",
                "priority": 5,
                "title": "Improve autoresearch evidence quality",
                "detail": (
                    "No specific failure found; inspect tests, reports, and memory for "
                    "a small reliability improvement."
                ),
            }
        )
    return sorted(candidates, key=lambda item: int(item.get("priority", 50)))[:10]


def scan_code_markers(workdir: Path, allowed_paths: list[str]) -> list[dict[str, Any]]:
    markers = ("TODO", "FIXME", "XXX")
    candidates: list[dict[str, Any]] = []
    for allowed in allowed_paths:
        base = workdir / allowed
        if not base.exists():
            continue
        paths = [base] if base.is_file() else list(base.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix in {".png", ".jpg", ".db", ".xlsx"}:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines, start=1):
                if any(marker in line for marker in markers):
                    rel = path.relative_to(workdir).as_posix()
                    candidates.append(
                        {
                            "source": "code_marker",
                            "priority": 20,
                            "title": f"Resolve marker in {rel}:{index}",
                            "file": rel,
                            "line": index,
                            "detail": line.strip()[:240],
                        }
                    )
                    break
    return candidates[:20]


def scan_recent_failures(workdir: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in sorted((workdir / "runs").glob("**/failure_report.json"), reverse=True)[:10]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidates.append(
            {
                "source": "failure_report",
                "priority": 10,
                "title": f"Repair failure from {path.relative_to(workdir).as_posix()}",
                "detail": str(payload.get("reason") or payload.get("error") or payload)[:400],
            }
        )
    return candidates


def search_memory(memory_url: str, query: str, limit: int) -> list[dict[str, Any]]:
    params = urlencode({"query": query, "project": "rpa-harness", "limit": limit})
    url = memory_url.rstrip("/") + "/api/search?" + params
    try:
        with urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    results = payload.get("results", {}) if isinstance(payload, dict) else {}
    candidates: list[dict[str, Any]] = []
    for group_name, group in results.items():
        if not isinstance(group, list):
            continue
        for item in group[:limit]:
            candidates.append(
                {
                    "source": f"memory:{group_name}",
                    "priority": 15,
                    "title": str(item.get("title") or item.get("summary") or "Memory candidate"),
                    "detail": str(item)[:500],
                }
            )
    return candidates


def build_supervisor_prompt(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
    candidates: list[dict[str, Any]],
) -> str:
    base_prompt = build_codex_prompt(autoresearch_config)
    return f"""{base_prompt}

Autonomous supervisor instructions:
- Work in this isolated worktree only.
- Pick exactly one candidate from the list below.
- Make the smallest production-safe improvement.
- Add or update a focused test when code changes.
- Run only targeted checks needed while editing; the supervisor will run the benchmark and gates.
- Do not commit, merge, push, reset, or edit files outside allowed paths.
- Stop after one scoped change.

Candidates:
{json.dumps(redact_value(candidates), indent=2)}
"""


def ensure_worktree(config: SupervisorConfig) -> CommandResult:
    if (config.worktree_path / ".git").exists() or (config.worktree_path / ".git").is_file():
        return CommandResult("worktree exists", 0, 0.0, "", "")

    config.worktree_path.parent.mkdir(parents=True, exist_ok=True)
    existing = run_git(config.git_binary, ["branch", "--list", config.branch_name], config.workdir)
    if existing.stdout.strip():
        return run_git(
            config.git_binary,
            ["worktree", "add", str(config.worktree_path), config.branch_name],
            config.workdir,
            timeout_seconds=60,
        )

    return run_git(
        config.git_binary,
        [
            "worktree",
            "add",
            "-b",
            config.branch_name,
            str(config.worktree_path),
            config.base_branch,
        ],
        config.workdir,
        timeout_seconds=60,
    )


def sync_autoresearch_files(config: SupervisorConfig) -> None:
    source = config.workdir / ".autoresearch"
    target = config.worktree_path / ".autoresearch"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "autoresearch.config.json",
        "autoresearch.md",
        "autoresearch.sh",
        "autoresearch.checks.sh",
        "autoresearch.ideas.md",
    ):
        source_path = source / name
        if source_path.exists():
            target_path = target / name
            target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            if source_path.stat().st_mode & 0o111:
                target_path.chmod(target_path.stat().st_mode | 0o111)


def run_review_gate(config: SupervisorConfig) -> dict[str, Any]:
    prompt = (
        "Review this uncommitted autoresearch diff as a blocking integration gate. "
        "Report only correctness, security, data-loss, credential, test, or merge-risk issues. "
        "If there are no blocking issues, say exactly: No blocking findings."
    )
    review = run_prompt_command(config.review_command, config.worktree_path, prompt, 1200)
    review_markdown_path = (
        config.worktree_path / config.review_markdown_path.relative_to(config.workdir)
    )
    review_file_output = read_text_if_exists(review_markdown_path)
    report = build_review_report(review, extra_output=review_file_output)
    review_path = config.worktree_path / config.review_json_path.relative_to(config.workdir)
    write_review_report(review_path, report)
    if not review.passed:
        return {"status": "review_failed", "review": report}
    if report["blocking_findings"]:
        return {"status": "review_blocked", "review": report}
    return {"status": "ok", "review": report}


def build_review_report(review: CommandResult, extra_output: str = "") -> dict[str, Any]:
    output = "\n".join(part for part in (review.combined_output(), extra_output) if part)
    lower = output.lower()
    blocking = [
        line.strip()
        for line in output.splitlines()
        if any(marker in line.lower() for marker in BLOCKING_REVIEW_MARKERS)
    ]
    return {
        "status": "ok" if review.passed and not blocking else "blocked",
        "blocking_findings": blocking,
        "non_blocking": (
            review.passed
            and not blocking
            and "no blocking findings" not in lower
            and bool(output.strip())
        ),
        "command": command_summary(review),
    }


def write_review_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(redact_value(report), indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def integration_gate(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
) -> dict[str, Any]:
    changed = changed_files(config.git_binary, config.worktree_path)
    if not changed:
        return {"status": "no_changes"}

    allowed_paths = set(autoresearch_config.allowed_paths)
    outside = [
        path for path in changed
        if not any(path.startswith(allowed) for allowed in allowed_paths)
    ]
    if outside:
        return {"status": "outside_allowed_paths", "files": outside}

    generated = [path for path in changed if path.startswith(GENERATED_PATH_PREFIXES)]
    if generated:
        return {"status": "generated_artifacts", "files": generated}

    leaked = secret_scan_files(config.worktree_path, changed)
    if leaked:
        return {"status": "secret_scan_failed", "files": leaked}

    return {"status": "ok", "files": changed}


def confidence_gate_failure(
    config: SupervisorConfig,
    latest_entry: dict[str, Any],
) -> dict[str, Any] | None:
    if config.min_confidence is None:
        return None
    confidence = latest_entry.get("confidence")
    if confidence is None or float(confidence) < config.min_confidence:
        return {
            "status": "low_confidence",
            "confidence": confidence,
            "minimum": config.min_confidence,
        }
    return None


def commit_worktree(config: SupervisorConfig, latest_entry: dict[str, Any]) -> CommandResult:
    add_result = run_git(config.git_binary, ["add", "-A"], config.worktree_path)
    if not add_result.passed:
        return add_result

    metric_name = latest_entry.get("metric_name", "metric")
    metric = latest_entry.get("metric", 0)
    message = (
        f"Improve autoresearch {metric_name}\n\n"
        f"Metric: {metric_name}={metric}\n"
        f"Status: {latest_entry.get('status')}\n"
        f"Lesson: {latest_entry.get('lesson', '')}"
    )
    return run_git(config.git_binary, ["commit", "-m", message], config.worktree_path)


def tag_winner(
    config: SupervisorConfig,
    commit_sha: str,
    latest_entry: dict[str, Any],
) -> CommandResult:
    if not commit_sha:
        return CommandResult("tag winner", 1, 0.0, "", "Missing commit")
    run_number = str(latest_entry.get("run", "unknown")).replace("/", "-")
    metric_name = str(latest_entry.get("metric_name", "metric")).replace("/", "-")
    tag = f"autoresearch/{config.session_id}/run-{run_number}-{metric_name}"
    message = (
        f"Autoresearch winner {run_number}\n\n"
        f"Metric: {metric_name}={latest_entry.get('metric')}\n"
        f"Lesson: {latest_entry.get('lesson', '')}"
    )
    return run_git(
        config.git_binary,
        ["tag", "-f", "-a", tag, commit_sha, "-m", message],
        config.worktree_path,
    )


def append_learning(
    config: SupervisorConfig,
    latest_entry: dict[str, Any],
    commit_sha: str,
) -> None:
    config.learnings_path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"- {datetime.now(timezone.utc).isoformat()} "
        f"`{commit_sha}` {latest_entry.get('metric_name')}={latest_entry.get('metric')}: "
        f"{latest_entry.get('lesson', '')}\n"
    )
    with config.learnings_path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def merge_to_main(config: SupervisorConfig) -> CommandResult:
    main_dirty = changed_files(config.git_binary, config.workdir)
    allowed_supervisor_files = {
        ".autoresearch/autoresearch.learnings.md",
        ".autoresearch/review.json",
        ".autoresearch/supervisor.jsonl",
        ".autoresearch/supervisor_plan.md",
    }
    blocking_dirty = [path for path in main_dirty if path not in allowed_supervisor_files]
    if blocking_dirty:
        return CommandResult(
            "merge preflight",
            1,
            0.0,
            "",
            "Main worktree has dirty files: " + ", ".join(blocking_dirty[:20]),
        )

    switch_result = run_git(config.git_binary, ["switch", config.base_branch], config.workdir)
    if not switch_result.passed:
        return switch_result

    update = update_main_from_remote(config)
    if not update.passed:
        return update

    rebase_result = update_worktree_from_main(config)
    if not rebase_result.passed:
        return rebase_result

    return run_git(config.git_binary, ["merge", "--ff-only", config.branch_name], config.workdir)


def update_main_from_remote(config: SupervisorConfig) -> CommandResult:
    fetch = run_git(config.git_binary, ["fetch", "origin", config.base_branch], config.workdir, 120)
    if not fetch.passed:
        return fetch
    remote_ref = f"origin/{config.base_branch}"
    local_sha = git_output(config.git_binary, ["rev-parse", config.base_branch], config.workdir)
    remote_sha = git_output(config.git_binary, ["rev-parse", remote_ref], config.workdir)
    if not remote_sha:
        return CommandResult("remote freshness", 0, 0.0, "", "No remote ref found")
    ancestor = run_git(
        config.git_binary,
        ["merge-base", "--is-ancestor", remote_ref, config.base_branch],
        config.workdir,
    )
    if ancestor.passed:
        return CommandResult("remote freshness", 0, 0.0, local_sha, "Remote is ancestor")
    local_ancestor = run_git(
        config.git_binary,
        ["merge-base", "--is-ancestor", config.base_branch, remote_ref],
        config.workdir,
    )
    if local_ancestor.passed:
        ff = run_git(
            config.git_binary,
            ["merge", "--ff-only", remote_ref],
            config.workdir,
            120,
        )
        return ff
    return CommandResult(
        "remote freshness",
        1,
        0.0,
        "",
        f"{config.base_branch} diverged from {remote_ref}",
    )


def update_worktree_from_main(config: SupervisorConfig) -> CommandResult:
    if not config.worktree_path.exists():
        return CommandResult("worktree update", 0, 0.0, "", "No worktree yet")
    return run_git(config.git_binary, ["rebase", config.base_branch], config.worktree_path, 120)


def remote_freshness_gate(config: SupervisorConfig) -> dict[str, Any]:
    update = update_main_from_remote(config)
    if not update.passed:
        return {"status": "remote_advanced_or_diverged", "update": command_summary(update)}
    remote_ref = f"origin/{config.base_branch}"
    ancestor = run_git(
        config.git_binary,
        ["merge-base", "--is-ancestor", remote_ref, config.base_branch],
        config.workdir,
    )
    if not ancestor.passed:
        return {"status": "remote_advanced_or_diverged", "check": command_summary(ancestor)}
    return {"status": "ok", "detail": "remote is ancestor of local main"}


def rollback_main_merge(config: SupervisorConfig, target_sha: str) -> CommandResult:
    if not target_sha:
        return CommandResult("rollback main merge", 1, 0.0, "", "Missing rollback target")
    switch_result = run_git(config.git_binary, ["switch", config.base_branch], config.workdir)
    if not switch_result.passed:
        return switch_result
    return run_git(config.git_binary, ["reset", "--hard", target_sha], config.workdir)


def run_hook(config: SupervisorConfig, event: str, payload: dict[str, Any]) -> CommandResult:
    path = config.hooks_dir / f"{event}.sh"
    if not path.exists():
        return CommandResult(f"hook {event}", 0, 0.0, "", "missing")
    if not os.access(path, os.X_OK):
        return CommandResult(f"hook {event}", 1, 0.0, "", f"{path} is not executable")
    return run_prompt_command(str(path), config.workdir, json.dumps(redact_value(payload)), 300)


def reset_worktree_and_audit(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
    result: dict[str, Any],
) -> dict[str, Any]:
    repair_worktree_to_main(config)
    return audit_and_return(config, autoresearch_config, result)


def repair_worktree_to_main(config: SupervisorConfig) -> None:
    if not config.worktree_path.exists():
        return
    run_git(config.git_binary, ["rebase", "--abort"], config.worktree_path)
    run_git(config.git_binary, ["merge", "--abort"], config.worktree_path)
    run_git(config.git_binary, ["reset", "--hard", config.base_branch], config.worktree_path)
    run_git(config.git_binary, ["clean", "-fd"], config.worktree_path)


def audit_and_return(
    config: SupervisorConfig,
    autoresearch_config: AutoresearchConfig,
    result: dict[str, Any],
) -> dict[str, Any]:
    entry = {
        "type": "supervisor",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": config.session_id,
        "branch": config.branch_name,
        "worktree": str(config.worktree_path),
        **result,
    }
    config.session_dir.mkdir(parents=True, exist_ok=True)
    with config.audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_value(entry), sort_keys=True) + "\n")
    run_hook(config, "after", entry)
    save_to_memory(autoresearch_config, memory_entry_for_supervisor(entry))
    return redact_value(entry)


def memory_entry_for_supervisor(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "run": entry.get("timestamp", "supervisor"),
        "status": entry.get("status", "unknown"),
        "metric_name": "autoresearch_supervisor",
        "type": "run",
        "metric": 0,
        "metrics": {},
        "direction": "higher",
        "objective": "Autonomous autoresearch supervision",
        "timestamp": entry.get("timestamp"),
        "lesson": f"Supervisor cycle ended with {entry.get('status')}",
        "heartbeat": [],
        "benchmark": None,
        "checks": None,
    }


def latest_run_entry(path: Path) -> dict[str, Any]:
    entries = read_jsonl(path)
    return entries[-1] if entries else {}


def read_supervisor_audit(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def changed_files(git_binary: str, cwd: Path) -> list[str]:
    result = run_git(git_binary, ["status", "--porcelain"], cwd)
    if not result.passed:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        files.append(path)
    return files


def secret_scan_files(root: Path, paths: list[str]) -> list[str]:
    leaked: list[str] = []
    for rel in paths:
        path = root / rel
        if not path.exists() or not path.is_file():
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".db", ".xlsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if any(pattern in text for pattern in SECRET_PATTERNS):
            leaked.append(rel)
    return leaked


def run_prompt_command(command: str, cwd: Path, prompt: str, timeout_seconds: int) -> CommandResult:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            executable="/bin/bash",
            text=True,
            input=prompt,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            duration_seconds=time.time() - started,
            stdout=completed.stdout[-12000:],
            stderr=completed.stderr[-12000:],
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            exit_code=None,
            duration_seconds=time.time() - started,
            stdout=(exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            timed_out=True,
        )


def run_git(
    git_binary: str,
    args: list[str],
    cwd: Path,
    timeout_seconds: int = 30,
) -> CommandResult:
    started = time.time()
    try:
        completed = subprocess.run(
            [git_binary, *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            command=" ".join([git_binary, *args]),
            exit_code=completed.returncode,
            duration_seconds=time.time() - started,
            stdout=completed.stdout[-12000:],
            stderr=completed.stderr[-12000:],
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=" ".join([git_binary, *args]),
            exit_code=None,
            duration_seconds=time.time() - started,
            stdout=(exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            timed_out=True,
        )


def git_output(git_binary: str, args: list[str], cwd: Path) -> str:
    result = run_git(git_binary, args, cwd)
    return result.stdout.strip() if result.passed else ""


def command_summary(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "duration_seconds": round(result.duration_seconds, 3),
        "timed_out": result.timed_out,
        "tail_output": redact_value(result.combined_output()[-4000:]),
    }


if __name__ == "__main__":
    raise SystemExit(main())
