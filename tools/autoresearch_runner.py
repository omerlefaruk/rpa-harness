#!/usr/bin/env python3
"""
Small, deterministic autoresearch runner for RPA Harness.

The runner does not ask an LLM to edit code by itself. It creates durable
session context, runs benchmark/check scripts, enforces heartbeat gates, and
records each result so a Codex session can implement one scoped change at a
time while this tool judges the outcome.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.security import redact_value

METRIC_RE = re.compile(r"^METRIC\s+([\w.µ]+)=(\S+)\s*$", re.MULTILINE)
DENIED_METRIC_NAMES = {"__proto__", "constructor", "prototype"}
DEFAULT_SESSION_DIR = ".autoresearch"
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_CHECKS_TIMEOUT_SECONDS = 300


@dataclass
class HeartbeatCheck:
    name: str
    status: str
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status in {"ok", "warn"}

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class CommandResult:
    command: str
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def combined_output(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part)


@dataclass
class AutoresearchConfig:
    workdir: Path
    session_dir: Path
    objective: str = "Improve RPA Harness reliability with measured, reversible changes."
    metric_name: str = "capability_pass_rate"
    metric_unit: str = ""
    direction: str = "higher"
    benchmark_command: str = "bash .autoresearch/autoresearch.sh"
    checks_command: str = "bash .autoresearch/autoresearch.checks.sh"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    checks_timeout_seconds: int = DEFAULT_CHECKS_TIMEOUT_SECONDS
    max_iterations: int | None = None
    memory_url: str = "http://127.0.0.1:37777"
    memory_required: bool = False
    allowed_paths: list[str] = field(default_factory=lambda: ["tools/", "tests/", "docs/"])

    @property
    def jsonl_path(self) -> Path:
        return self.session_dir / "autoresearch.jsonl"

    @property
    def markdown_path(self) -> Path:
        return self.session_dir / "autoresearch.md"

    @property
    def ideas_path(self) -> Path:
        return self.session_dir / "autoresearch.ideas.md"

    @property
    def prompt_path(self) -> Path:
        return self.session_dir / "codex_prompt.md"


def main() -> int:
    args = parse_args()
    config = load_config(args.config, Path(args.workdir).resolve())

    if args.init:
        init_session(config, force=args.force)

    if args.next_prompt:
        config.prompt_path.write_text(build_codex_prompt(config), encoding="utf-8")
        print(config.prompt_path)

    if args.heartbeat:
        checks = run_heartbeat(config)
        print(json.dumps({"heartbeat": [check.to_dict() for check in checks]}, indent=2))
        return 0 if all(check.passed for check in checks) else 1

    if args.once:
        return run_once(config)

    if not any((args.init, args.next_prompt, args.heartbeat, args.once)):
        print("Nothing to do. Use --init, --next-prompt, --heartbeat, or --once.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a deterministic autoresearch iteration")
    parser.add_argument("--config", default=None, help="Optional autoresearch config JSON")
    parser.add_argument("--workdir", default=".", help="Repository working directory")
    parser.add_argument("--init", action="store_true", help="Create session template files")
    parser.add_argument("--force", action="store_true", help="Overwrite template files during init")
    parser.add_argument("--next-prompt", action="store_true", help="Write a scoped Codex prompt")
    parser.add_argument("--heartbeat", action="store_true", help="Run heartbeat checks only")
    parser.add_argument("--once", action="store_true", help="Run one benchmark/check/log iteration")
    return parser.parse_args()


def load_config(config_path: str | None, workdir: Path) -> AutoresearchConfig:
    session_dir = workdir / DEFAULT_SESSION_DIR
    data: dict[str, Any] = {}
    if config_path:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    elif (session_dir / "autoresearch.config.json").exists():
        data = json.loads((session_dir / "autoresearch.config.json").read_text(encoding="utf-8"))

    configured_workdir = Path(data.get("workdir", workdir))
    if not configured_workdir.is_absolute():
        configured_workdir = (workdir / configured_workdir).resolve()

    configured_session_dir = Path(data.get("session_dir", DEFAULT_SESSION_DIR))
    if not configured_session_dir.is_absolute():
        configured_session_dir = (configured_workdir / configured_session_dir).resolve()

    return AutoresearchConfig(
        workdir=configured_workdir,
        session_dir=configured_session_dir,
        objective=data.get(
            "objective",
            "Improve RPA Harness reliability with measured, reversible changes.",
        ),
        metric_name=data.get("metric_name", "capability_pass_rate"),
        metric_unit=data.get("metric_unit", ""),
        direction=data.get("direction", "higher"),
        benchmark_command=data.get("benchmark_command", "bash .autoresearch/autoresearch.sh"),
        checks_command=data.get("checks_command", "bash .autoresearch/autoresearch.checks.sh"),
        timeout_seconds=int(data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        checks_timeout_seconds=int(
            data.get("checks_timeout_seconds", DEFAULT_CHECKS_TIMEOUT_SECONDS)
        ),
        max_iterations=data.get("max_iterations"),
        memory_url=data.get("memory_url", "http://127.0.0.1:37777"),
        memory_required=bool(data.get("memory_required", False)),
        allowed_paths=list(data.get("allowed_paths", ["tools/", "tests/", "docs/"])),
    )


def init_session(config: AutoresearchConfig, force: bool = False) -> None:
    config.session_dir.mkdir(parents=True, exist_ok=True)
    write_template(
        config.markdown_path,
        session_markdown_template(config),
        force=force,
    )
    write_template(
        config.session_dir / "autoresearch.sh",
        benchmark_script_template(config),
        force=force,
        executable=True,
    )
    write_template(
        config.session_dir / "autoresearch.checks.sh",
        checks_script_template(),
        force=force,
        executable=True,
    )
    write_template(
        config.ideas_path,
        "# Autoresearch Ideas\n\n- [ ] Improve failure report completeness scoring.\n",
        force=force,
    )
    write_template(
        config.session_dir / "autoresearch.config.json",
        json.dumps(
            {
                "objective": config.objective,
                "metric_name": config.metric_name,
                "metric_unit": config.metric_unit,
                "direction": config.direction,
                "benchmark_command": config.benchmark_command,
                "checks_command": config.checks_command,
                "allowed_paths": config.allowed_paths,
                "memory_url": config.memory_url,
                "memory_required": config.memory_required,
            },
            indent=2,
        )
        + "\n",
        force=force,
    )


def write_template(path: Path, content: str, force: bool = False, executable: bool = False) -> None:
    if path.exists() and not force:
        return
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | 0o111)


def session_markdown_template(config: AutoresearchConfig) -> str:
    return f"""# Autoresearch: RPA Harness Continuous Improvement

## Objective
{config.objective}

## Primary Metric
- `{config.metric_name}` ({config.metric_unit or "unitless"}, {config.direction} is better)

## How To Run
- Benchmark: `{config.benchmark_command}`
- Checks: `{config.checks_command}`

## Files In Scope
{chr(10).join(f"- `{path}`" for path in config.allowed_paths)}

## Off Limits
- Raw credentials, `.env`, generated reports/runs/data files.
- Core protected runtime paths unless a reproduced failure and test justify the change.
- Broad rewrites or new dependencies without a measured need.

## Keep Rules
- Keep only when the primary metric improves and checks pass.
- Re-run marginal wins if confidence is low.
- Discard or revert crashes, checks failures, secret leaks, and unmeasured changes.

## What's Been Tried
- Baseline not recorded yet.
"""


def benchmark_script_template(config: AutoresearchConfig) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

start="$(python3 - <<'PY'
import time
print(time.time())
PY
)"

python3 -m py_compile harness/*.py harness/**/*.py main.py >/dev/null
python3 -m pytest -q tests/test_security.py tests/test_memory.py >/dev/null

end="$(python3 - <<'PY'
import time
print(time.time())
PY
)"

python3 - <<PY
start = float("$start")
end = float("$end")
print("METRIC {config.metric_name}=1")
print(f"METRIC default_cli_seconds={{end - start:.3f}}")
PY
"""


def checks_script_template() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile harness/*.py harness/**/*.py main.py
python3 -m pytest -q tests/test_security.py tests/test_memory.py
"""


def run_once(config: AutoresearchConfig) -> int:
    checks = run_heartbeat(config)
    hard_failures = [check for check in checks if check.status == "fail"]
    if hard_failures:
        print(json.dumps({"status": "heartbeat_failed", "heartbeat": serialize_checks(checks)}, indent=2))
        return 1

    benchmark = run_command(config.benchmark_command, config.workdir, config.timeout_seconds)
    metrics = parse_metric_lines(benchmark.combined_output())
    checks_result: CommandResult | None = None
    if benchmark.passed:
        checks_result = run_command(
            config.checks_command,
            config.workdir,
            config.checks_timeout_seconds,
        )

    previous = read_jsonl(config.jsonl_path)
    entry = build_run_entry(
        config=config,
        previous=previous,
        heartbeat=checks,
        benchmark=benchmark,
        checks_result=checks_result,
        metrics=metrics,
    )
    append_jsonl(config.jsonl_path, entry)
    save_to_memory(config, entry)
    print(json.dumps(entry, indent=2))
    return 0 if entry["status"] == "keep" else 1


def run_heartbeat(config: AutoresearchConfig) -> list[HeartbeatCheck]:
    checks = [
        heartbeat_session_files(config),
        heartbeat_memory(config),
        heartbeat_budget(config),
        heartbeat_git_scope(config),
        heartbeat_secret_scan(config),
    ]
    return checks


def heartbeat_session_files(config: AutoresearchConfig) -> HeartbeatCheck:
    missing = [
        str(path.relative_to(config.workdir))
        for path in (config.markdown_path, config.session_dir / "autoresearch.sh")
        if not path.exists()
    ]
    if missing:
        return HeartbeatCheck("session_files", "fail", f"Missing: {', '.join(missing)}")
    return HeartbeatCheck("session_files", "ok")


def heartbeat_memory(config: AutoresearchConfig) -> HeartbeatCheck:
    url = config.memory_url.rstrip("/") + "/health"
    try:
        with urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        status = "fail" if config.memory_required else "warn"
        return HeartbeatCheck("memory", status, f"Memory unavailable: {exc}")
    if payload.get("status") != "ok":
        status = "fail" if config.memory_required else "warn"
        return HeartbeatCheck("memory", status, f"Unexpected health payload: {payload}")
    return HeartbeatCheck("memory", "ok")


def heartbeat_budget(config: AutoresearchConfig) -> HeartbeatCheck:
    if config.max_iterations is None:
        return HeartbeatCheck("budget", "ok")
    run_count = len(read_jsonl(config.jsonl_path))
    if run_count >= config.max_iterations:
        return HeartbeatCheck("budget", "fail", f"Max iterations reached: {run_count}")
    return HeartbeatCheck("budget", "ok", f"{run_count}/{config.max_iterations}")


def heartbeat_git_scope(config: AutoresearchConfig) -> HeartbeatCheck:
    proxy = Path("/Users/rau/bin/codex-git-proxy")
    if not proxy.exists():
        return HeartbeatCheck("git_scope", "warn", "codex-git-proxy not found")
    result = subprocess.run(
        [str(proxy), "status", "--porcelain"],
        cwd=config.workdir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return HeartbeatCheck("git_scope", "warn", result.stderr.strip()[:300])
    changed = [line[3:] for line in result.stdout.splitlines() if len(line) > 3]
    outside = [
        path for path in changed
        if path and not any(path.startswith(allowed) for allowed in config.allowed_paths)
    ]
    if outside:
        return HeartbeatCheck(
            "git_scope",
            "warn",
            "Dirty files outside autoresearch scope: " + ", ".join(outside[:8]),
        )
    return HeartbeatCheck("git_scope", "ok")


def heartbeat_secret_scan(config: AutoresearchConfig) -> HeartbeatCheck:
    paths = [config.jsonl_path, config.markdown_path]
    leaked = []
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        leaked_secret = re.search(
            r"(?i)(Bearer\s+(?!\[REDACTED\])\S+|"
            r"password\s*[=:]\s*(?!\[REDACTED\])\S+|"
            r"api[_-]?key\s*[=:]\s*(?!\[REDACTED\])\S+)",
            text,
        )
        if leaked_secret:
            leaked.append(str(path.relative_to(config.workdir)))
    if leaked:
        return HeartbeatCheck("secret_scan", "fail", "Sensitive-looking content in " + ", ".join(leaked))
    return HeartbeatCheck("secret_scan", "ok")


def run_command(command: str, cwd: Path, timeout_seconds: int) -> CommandResult:
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            executable="/bin/bash",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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


def parse_metric_lines(output: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for match in METRIC_RE.finditer(output):
        name, raw_value = match.groups()
        if name in DENIED_METRIC_NAMES:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue
        if math.isfinite(value):
            metrics[name] = value
    return metrics


def build_run_entry(
    config: AutoresearchConfig,
    previous: list[dict[str, Any]],
    heartbeat: list[HeartbeatCheck],
    benchmark: CommandResult,
    checks_result: CommandResult | None,
    metrics: dict[str, float],
) -> dict[str, Any]:
    primary_metric = metrics.get(config.metric_name)
    status = decide_status(
        metric=primary_metric,
        benchmark_passed=benchmark.passed,
        checks_passed=(checks_result.passed if checks_result else False),
        previous=previous,
        direction=config.direction,
    )
    run_number = len(previous) + 1
    entry = {
        "type": "run",
        "run": run_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "objective": config.objective,
        "metric_name": config.metric_name,
        "metric": primary_metric if primary_metric is not None else 0,
        "metrics": metrics,
        "direction": config.direction,
        "status": status,
        "confidence": compute_confidence(previous + [{"metric": primary_metric or 0, "status": status}], config.direction),
        "heartbeat": serialize_checks(heartbeat),
        "benchmark": command_summary(benchmark),
        "checks": command_summary(checks_result) if checks_result else None,
        "lesson": lesson_for(status, benchmark, checks_result, metrics, config.metric_name),
    }
    return redact_value(entry)


def decide_status(
    metric: float | None,
    benchmark_passed: bool,
    checks_passed: bool,
    previous: list[dict[str, Any]],
    direction: str,
) -> str:
    if not benchmark_passed or metric is None:
        return "crash"
    if not checks_passed:
        return "checks_failed"
    best = best_kept_metric(previous, direction)
    if best is None:
        return "keep"
    if is_better(metric, best, direction):
        return "keep"
    return "discard"


def best_kept_metric(entries: list[dict[str, Any]], direction: str) -> float | None:
    kept = [
        float(entry["metric"])
        for entry in entries
        if entry.get("status") == "keep" and isinstance(entry.get("metric"), (int, float))
    ]
    if not kept:
        return None
    return min(kept) if direction == "lower" else max(kept)


def is_better(metric: float, best: float, direction: str) -> bool:
    return metric < best if direction == "lower" else metric > best


def compute_confidence(entries: list[dict[str, Any]], direction: str) -> float | None:
    values = [
        float(entry["metric"])
        for entry in entries
        if isinstance(entry.get("metric"), (int, float)) and float(entry["metric"]) > 0
    ]
    if len(values) < 3:
        return None
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    if mad == 0:
        return None
    baseline = values[0]
    best = min(values) if direction == "lower" else max(values)
    return round(abs(best - baseline) / mad, 3)


def command_summary(result: CommandResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "duration_seconds": round(result.duration_seconds, 3),
        "timed_out": result.timed_out,
        "tail_output": redact_value(result.combined_output()[-4000:]),
    }


def lesson_for(
    status: str,
    benchmark: CommandResult,
    checks_result: CommandResult | None,
    metrics: dict[str, float],
    metric_name: str,
) -> str:
    if status == "keep":
        return f"Accepted measured result for {metric_name}: {metrics.get(metric_name)}"
    if status == "checks_failed":
        return "Benchmark produced a metric, but correctness checks failed."
    if status == "crash":
        if benchmark.timed_out:
            return "Benchmark timed out before producing an acceptable result."
        return "Benchmark crashed or did not emit the primary metric."
    return "Measured result did not improve the best kept metric."


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("type") == "run":
            entries.append(parsed)
    return entries


def append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_value(entry), sort_keys=True) + "\n")


def save_to_memory(config: AutoresearchConfig, entry: dict[str, Any]) -> None:
    url = config.memory_url.rstrip("/") + "/api/memory/save"
    payload = {
        "project": "rpa-harness",
        "title": f"Autoresearch run {entry['run']}: {entry['status']}",
        "text": json.dumps(redact_value(entry), sort_keys=True),
        "metadata": {
            "type": "autoresearch",
            "run": entry["run"],
            "status": entry["status"],
            "metric_name": entry["metric_name"],
        },
    }
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=2):
            return
    except (OSError, URLError, TimeoutError):
        if config.memory_required:
            raise


def build_codex_prompt(config: AutoresearchConfig) -> str:
    entries = read_jsonl(config.jsonl_path)
    recent = entries[-5:]
    ideas = config.ideas_path.read_text(encoding="utf-8") if config.ideas_path.exists() else ""
    return f"""You are implementing one measured RPA Harness autoresearch experiment.

Objective:
{config.objective}

Primary metric:
- {config.metric_name} ({config.direction} is better)

Allowed paths:
{chr(10).join(f"- {path}" for path in config.allowed_paths)}

Rules:
- Make one small change only.
- Add or update a focused test when code changes.
- Do not touch credentials or generated reports/runs/data files.
- Do not edit protected harness/runtime paths unless a reproduced failure and test justify it.
- After editing, stop. The autoresearch runner will measure and decide keep/discard.

Recent runs:
{json.dumps(redact_value(recent), indent=2)}

Ideas:
{ideas}
"""


def serialize_checks(checks: list[HeartbeatCheck]) -> list[dict[str, Any]]:
    return [check.to_dict() for check in checks]


if __name__ == "__main__":
    raise SystemExit(main())
