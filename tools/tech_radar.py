#!/usr/bin/env python3
"""Heartbeat-driven technology radar for the RPA harness.

The radar watches a small set of authoritative technology sources and turns
changes into reviewable improvement candidates. It is intentionally read-only:
it never changes dependencies, workflows, or production code by itself. The
autoresearch supervisor can use the generated candidates as input, then apply
its normal worktree, test, review, and merge gates.
"""

from __future__ import annotations

import argparse
import dataclasses
import contextlib
import email.utils
import hashlib
import html
import json
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:  # Keep this tool usable as a standalone stdlib script.
    from harness.security import redact_value
except Exception:  # pragma: no cover - fallback for isolated execution

    def redact_value(value: Any, *args: Any, **kwargs: Any) -> Any:
        return value


DEFAULT_USER_AGENT = "rpa-harness-tech-radar/1.0 (+https://local.invalid/rpa-harness)"
DEFAULT_MAX_BYTES = 512_000
DEFAULT_TIMEOUT_SECONDS = 10.0
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
WHITESPACE_RE = re.compile(r"\s+")


@dataclasses.dataclass(frozen=True)
class TechSource:
    name: str
    url: str
    category: str = "general"
    kind: str = "html"
    max_bytes: int = DEFAULT_MAX_BYTES
    tags: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TechSource":
        name = str(raw.get("name", "")).strip()
        url = sanitize_url(str(raw.get("url", "")).strip())
        if not name:
            raise ValueError("source is missing name")
        if not urlsplit(url).scheme:
            raise ValueError(f"source {name!r} is missing an absolute URL")
        tags = tuple(str(tag).strip() for tag in raw.get("tags", []) if str(tag).strip())
        max_bytes = int(raw.get("max_bytes", DEFAULT_MAX_BYTES) or DEFAULT_MAX_BYTES)
        return cls(
            name=name,
            url=url,
            category=str(raw.get("category", "general")).strip() or "general",
            kind=str(raw.get("kind", "html")).strip().lower() or "html",
            max_bytes=max(4096, min(max_bytes, 2_000_000)),
            tags=tags,
        )


def sanitize_url(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def load_sources(config_path: Path) -> list[TechSource]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw_sources = raw.get("sources", [])
    elif isinstance(raw, list):
        raw_sources = raw
    else:
        raise ValueError("tech radar config must be a list or an object with a sources list")
    return [TechSource.from_mapping(item) for item in raw_sources]


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "sources": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "sources": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "sources": {}}
    raw.setdefault("version", 1)
    raw.setdefault("sources", {})
    if not isinstance(raw["sources"], dict):
        raw["sources"] = {}
    return raw


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def append_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(redact_value(event), sort_keys=True, default=str) + "\n")


@contextlib.contextmanager
def per_source_deadline(seconds: float):
    """Best-effort wall-clock deadline for network calls on Unix-like runners."""
    if (
        seconds <= 0
        or not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def _raise_timeout(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"technology radar source exceeded {seconds:.1f}s deadline")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    signal.signal(signal.SIGALRM, _raise_timeout)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])
        signal.signal(signal.SIGALRM, previous_handler)


def fetch_source(source: TechSource, timeout: float) -> tuple[bytes, dict[str, str]]:
    curl = shutil.which("curl")
    if curl:
        return fetch_source_with_curl(source, timeout=timeout, curl=curl)
    return fetch_source_with_urllib(source, timeout=timeout)


def fetch_source_with_curl(
    source: TechSource,
    *,
    timeout: float,
    curl: str,
) -> tuple[bytes, dict[str, str]]:
    cmd = [
        curl,
        "--silent",
        "--show-error",
        "--location",
        "--max-time",
        str(max(1.0, timeout)),
        "--user-agent",
        DEFAULT_USER_AGENT,
        "--header",
        "Accept: text/html,application/xhtml+xml,application/xml,text/xml,text/plain,*/*",
        source.url,
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            timeout=max(1.5, timeout + 1.0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"curl exceeded {timeout:.1f}s for {source.name}") from exc
    if completed.returncode != 0:
        reason = completed.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(reason or f"curl failed with exit code {completed.returncode}")
    return completed.stdout[: source.max_bytes], {}


def fetch_source_with_urllib(source: TechSource, timeout: float) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(
        source.url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,text/plain,*/*",
        },
    )
    with per_source_deadline(max(1.0, timeout + 1.0)):
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
            return response.read(source.max_bytes + 1)[: source.max_bytes], headers


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def decode_body(body: bytes, headers: dict[str, str] | None = None) -> str:
    charset = None
    content_type = (headers or {}).get("content-type", "")
    match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type)
    if match:
        charset = match.group(1)
    for encoding in [charset, "utf-8", "latin-1"]:
        if not encoding:
            continue
        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def compact_text(value: str, max_chars: int = 220) -> str:
    value = html.unescape(WHITESPACE_RE.sub(" ", value)).strip()
    if len(value) > max_chars:
        return value[: max_chars - 15].rstrip() + "...[truncated]"
    return value


def extract_summary(source: TechSource, body: bytes, headers: dict[str, str] | None = None) -> dict[str, Any]:
    text = decode_body(body, headers)
    if source.kind in {"rss", "atom", "xml"} or text.lstrip().startswith("<?xml"):
        summary = extract_xml_summary(text)
        if summary:
            return summary
    match = TITLE_RE.search(text)
    if match:
        return {"title": compact_text(re.sub(r"<[^>]+>", " ", match.group(1)))}
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "untitled")
    return {"title": compact_text(first_line)}


def extract_xml_summary(text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {}

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    titles: list[str] = []
    for element in root.iter():
        if local_name(element.tag) == "title" and element.text:
            titles.append(compact_text(element.text))
        if len(titles) >= 6:
            break
    if not titles:
        return {}
    return {"title": titles[0], "recent_titles": titles[1:6]}


def utc_timestamp(now: float | None = None) -> str:
    return email.utils.formatdate(now or time.time(), usegmt=True)


def candidate_line(event: dict[str, Any]) -> str:
    tags = ", ".join(event.get("tags") or []) or "untagged"
    return (
        f"- [ ] Investigate {event['source_name']}: {event.get('title', 'updated source')} "
        f"({event.get('category', 'general')}; tags: {tags})"
    )


def append_candidates(path: Path, events: list[dict[str, Any]], *, now: float | None = None) -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {utc_timestamp(now)}\n")
        for event in events:
            handle.write(candidate_line(event) + "\n")


def select_sources_for_run(
    sources: list[TechSource],
    state: dict[str, Any],
    *,
    max_sources: int | None = None,
    cycle_size: int | None = None,
) -> list[TechSource]:
    if max_sources is not None:
        sources = sources[: max(0, max_sources)]
    if not sources or cycle_size is None:
        return sources
    count = min(max(0, cycle_size), len(sources))
    if count == 0:
        return []
    cursor = int(state.get("source_cursor", 0) or 0) % len(sources)
    selected = [sources[(cursor + index) % len(sources)] for index in range(count)]
    state["source_cursor"] = (cursor + count) % len(sources)
    state["source_cursor_total"] = len(sources)
    return selected


def run_radar(
    *,
    config_path: Path,
    state_path: Path,
    jsonl_path: Path,
    candidates_path: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_sources: int | None = None,
    cycle_size: int | None = None,
    strict: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    all_sources = load_sources(config_path)
    state = load_state(state_path)
    sources = select_sources_for_run(
        all_sources,
        state,
        max_sources=max_sources,
        cycle_size=cycle_size,
    )
    source_state: dict[str, Any] = state.setdefault("sources", {})
    events: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    scanned = 0

    for source in sources:
        scanned += 1
        key = source.url
        previous = source_state.get(key, {}) if isinstance(source_state.get(key), dict) else {}
        try:
            body, headers = fetch_source(source, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            unavailable.append(
                {
                    "source_name": source.name,
                    "url": source.url,
                    "category": source.category,
                    "status": "unavailable",
                    "reason": compact_text(str(exc), 180),
                }
            )
            continue

        digest = body_hash(body)
        summary = extract_summary(source, body, headers)
        changed = digest != previous.get("hash")
        source_state[key] = {
            "name": source.name,
            "url": source.url,
            "category": source.category,
            "kind": source.kind,
            "hash": digest,
            "title": summary.get("title", "untitled"),
            "last_seen_at": utc_timestamp(now),
            "tags": list(source.tags),
        }
        if changed:
            events.append(
                {
                    "event": "source_changed",
                    "source_name": source.name,
                    "url": source.url,
                    "category": source.category,
                    "kind": source.kind,
                    "tags": list(source.tags),
                    "title": summary.get("title", "untitled"),
                    "recent_titles": summary.get("recent_titles", []),
                    "hash": digest,
                    "previous_hash": previous.get("hash"),
                    "changed_at": utc_timestamp(now),
                }
            )

    state["last_run_at"] = utc_timestamp(now)
    state["last_run"] = {
        "total_sources": len(all_sources),
        "scanned": scanned,
        "changed": len(events),
        "unavailable": len(unavailable),
    }
    write_json(state_path, redact_value(state))
    append_jsonl(jsonl_path, events)
    if candidates_path:
        append_candidates(candidates_path, events, now=now)

    summary = {
        "status": "failed" if strict and unavailable else "ok",
        "total_sources": len(all_sources),
        "scanned": scanned,
        "changed": len(events),
        "unavailable": len(unavailable),
        "state": str(state_path),
        "events": str(jsonl_path),
        "candidates": str(candidates_path) if candidates_path else None,
    }
    if unavailable:
        summary["unavailable_sources"] = unavailable
    if events:
        summary["changed_sources"] = [event["source_name"] for event in events]
    return redact_value(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RPA harness technology radar once")
    parser.add_argument("--config", default=".autoresearch/tech_radar.sources.json")
    parser.add_argument("--state", default=".autoresearch/tech_radar.state.json")
    parser.add_argument("--jsonl", default=".autoresearch/tech_radar.jsonl")
    parser.add_argument("--candidates", default=".autoresearch/tech_radar_candidates.md")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-sources", type=int)
    parser.add_argument(
        "--cycle-size",
        type=int,
        help="Scan only N sources this run and advance a persistent cursor",
    )
    parser.add_argument("--strict", action="store_true", help="Fail when any source is unavailable")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run_radar(
        config_path=Path(args.config),
        state_path=Path(args.state),
        jsonl_path=Path(args.jsonl),
        candidates_path=Path(args.candidates) if args.candidates else None,
        timeout=args.timeout,
        max_sources=args.max_sources,
        cycle_size=args.cycle_size,
        strict=args.strict,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 1 if summary.get("status") == "failed" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
