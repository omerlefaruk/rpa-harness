#!/usr/bin/env python3
"""Validate and refresh the repo's OKF markdown bundle."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

RESERVED_FILES = {"index.md", "log.md"}
DATE_HEADING_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}\s*$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def parse_markdown(path: str | Path) -> dict[str, Any]:
    md_path = Path(path)
    text = _read_text(md_path)
    if not text.startswith("---\n"):
        return {"frontmatter": None, "body": text, "has_frontmatter": False}
    try:
        _, raw_frontmatter, body = text.split("---\n", 2)
    except ValueError:
        return {
            "frontmatter": None,
            "body": text,
            "has_frontmatter": True,
            "error": "frontmatter is not closed",
        }
    try:
        frontmatter = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        return {
            "frontmatter": None,
            "body": body,
            "has_frontmatter": True,
            "error": f"frontmatter is not parseable YAML: {exc}",
        }
    return {"frontmatter": frontmatter, "body": body, "has_frontmatter": True}


def validate_bundle(root: str | Path, *, require_root_files: bool = True) -> dict[str, Any]:
    bundle = Path(root)
    errors: list[str] = []
    warnings: list[str] = []
    concept_count = 0
    if not bundle.exists():
        return {
            "status": "failed",
            "root": str(bundle),
            "concept_count": 0,
            "errors": [f"{bundle}: bundle root does not exist"],
            "warnings": [],
        }
    if require_root_files:
        if not (bundle / "index.md").exists():
            errors.append("index.md is required at the bundle root")
        if not (bundle / "log.md").exists():
            errors.append("log.md is required at the bundle root")

    for path in sorted(bundle.rglob("*.md")):
        rel = path.relative_to(bundle).as_posix()
        parsed = parse_markdown(path)
        if parsed.get("error"):
            errors.append(f"{rel}: {parsed['error']}")
            continue
        if path.name == "index.md":
            errors.extend(
                _validate_index(
                    bundle,
                    path,
                    parsed,
                    require_version=require_root_files and path.parent == bundle,
                )
            )
            if require_root_files:
                errors.extend(_validate_index_freshness(bundle, path))
        elif path.name == "log.md":
            errors.extend(_validate_log(bundle, path, parsed))
        else:
            concept_count += 1
            errors.extend(_validate_concept(bundle, path, parsed))
            warnings.extend(_broken_link_warnings(bundle, path, parsed["body"]))

    return {
        "status": "failed" if errors else "passed",
        "root": str(bundle),
        "concept_count": concept_count,
        "errors": errors,
        "warnings": warnings,
    }


def build_index_text(root: str | Path, directory: str | Path) -> str:
    bundle = Path(root)
    current = Path(directory)
    rel_dir = "." if current == bundle else current.relative_to(bundle).as_posix()
    lines: list[str] = []
    if current == bundle:
        lines.extend(['---', 'okf_version: "0.1"', '---', ""])
    title = "OKF Index" if current == bundle else f"OKF Index: {rel_dir}"
    lines.extend([f"# {title}", ""])

    directories = sorted(
        child for child in current.iterdir()
        if child.is_dir() and any(child.rglob("*.md"))
    )
    concepts = sorted(
        child for child in current.glob("*.md")
        if child.name not in RESERVED_FILES
    )

    if directories:
        lines.extend(["## Directories", ""])
        for child in directories:
            rel = child.relative_to(current).as_posix()
            lines.append(f"* [{child.name}]({rel}/) - OKF concepts in `{rel}/`.")
        lines.append("")

    if concepts:
        lines.extend(["## Concepts", ""])
        for concept in concepts:
            parsed = parse_markdown(concept)
            frontmatter = parsed.get("frontmatter") or {}
            title_value = frontmatter.get("title") or _title_from_stem(concept.stem)
            description = frontmatter.get("description") or "No description provided."
            lines.append(f"* [{title_value}]({concept.name}) - {description}")
        lines.append("")

    if not directories and not concepts:
        lines.extend(["No concepts in this directory yet.", ""])
    return "\n".join(lines).rstrip() + "\n"


def generate_indexes(root: str | Path) -> list[str]:
    bundle = Path(root)
    written: list[str] = []
    for directory in sorted(
        {bundle, *[path.parent for path in bundle.rglob("*.md") if path.name not in RESERVED_FILES]}
    ):
        if not directory.exists():
            continue
        text = build_index_text(bundle, directory)
        index_path = directory / "index.md"
        index_path.write_text(text, encoding="utf-8")
        written.append(str(index_path))
    return written


def _validate_concept(root: Path, path: Path, parsed: dict[str, Any]) -> list[str]:
    rel = path.relative_to(root).as_posix()
    frontmatter = parsed.get("frontmatter")
    if not parsed.get("has_frontmatter"):
        return [f"{rel}: missing YAML frontmatter"]
    if not isinstance(frontmatter, dict):
        return [f"{rel}: frontmatter must be a YAML mapping"]
    if not str(frontmatter.get("type") or "").strip():
        return [f"{rel}: missing required type"]
    return []


def _validate_index(
    root: Path,
    path: Path,
    parsed: dict[str, Any],
    *,
    require_version: bool = False,
) -> list[str]:
    rel = path.relative_to(root).as_posix()
    errors = []
    if path.parent != root and parsed.get("has_frontmatter"):
        errors.append(f"{rel}: index.md frontmatter is allowed only at the bundle root")
    if require_version and not parsed.get("has_frontmatter"):
        errors.append(f'{rel}: root index okf_version must be "0.1"')
    if path.parent == root and parsed.get("has_frontmatter"):
        version = (parsed.get("frontmatter") or {}).get("okf_version")
        if version != "0.1":
            errors.append(f'{rel}: root index okf_version must be "0.1"')
    body = parsed.get("body") or ""
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if first and not first.startswith("#"):
        errors.append(f"{rel}: index body must start with a heading")
    return errors


def _validate_index_freshness(root: Path, path: Path) -> list[str]:
    expected = build_index_text(root, path.parent)
    if _read_text(path) != expected:
        rel = path.relative_to(root).as_posix()
        return [f"{rel}: index is stale; run python scripts/okf.py generate-indexes docs/okf"]
    return []


def _validate_log(root: Path, path: Path, parsed: dict[str, Any]) -> list[str]:
    rel = path.relative_to(root).as_posix()
    errors = []
    if parsed.get("has_frontmatter"):
        errors.append(f"{rel}: log.md must not have frontmatter")
    body = parsed.get("body") or ""
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if first and not first.startswith("#"):
        errors.append(f"{rel}: log body must start with a heading")
    for line in body.splitlines():
        if line.startswith("## ") and not DATE_HEADING_RE.match(line.strip()):
            errors.append(f"{rel}: log heading must use YYYY-MM-DD: {line.strip()}")
    return errors


def _broken_link_warnings(root: Path, path: Path, body: str) -> list[str]:
    warnings = []
    root_resolved = root.resolve()
    for raw_target in LINK_RE.findall(body):
        target = raw_target.split("#", 1)[0].strip()
        if not target or _is_external_link(target) or not target.endswith(".md"):
            continue
        resolved = root / target.lstrip("/") if target.startswith("/") else path.parent / target
        try:
            resolved.resolve(strict=False).relative_to(root_resolved)
        except ValueError:
            continue
        if not resolved.exists():
            rel = path.relative_to(root).as_posix()
            warnings.append(f"{rel}: broken OKF link {raw_target}")
    return warnings


def _is_external_link(target: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _title_from_stem(stem: str) -> str:
    return " ".join(part.capitalize() for part in stem.replace("_", "-").split("-") if part)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or refresh an OKF bundle")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("root", nargs="?", default="docs/okf")
    index_parser = subparsers.add_parser("generate-indexes")
    index_parser.add_argument("root", nargs="?", default="docs/okf")
    args = parser.parse_args(argv)

    if args.command == "generate-indexes":
        written = generate_indexes(args.root)
        print(json.dumps({"status": "passed", "written": written}, indent=2))
        return 0

    result = validate_bundle(args.root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
