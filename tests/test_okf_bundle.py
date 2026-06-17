from __future__ import annotations

import json
from pathlib import Path

from scripts.okf import build_index_text, validate_bundle


def test_validate_bundle_rejects_concept_without_type(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "bad.md").write_text("---\ntitle: Bad\n---\n\nBody\n", encoding="utf-8")

    result = validate_bundle(bundle, require_root_files=False)

    assert result["status"] == "failed"
    assert any("missing required type" in error for error in result["errors"])


def test_validate_bundle_allows_broken_concept_links_as_warnings(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "concept.md").write_text(
        "---\ntype: Reference\ntitle: Concept\n---\n\nSee [missing](/missing.md).\n",
        encoding="utf-8",
    )

    result = validate_bundle(bundle, require_root_files=False)

    assert result["status"] == "passed"
    assert result["warnings"] == ["concept.md: broken OKF link /missing.md"]


def test_validate_bundle_rejects_bad_log_date_heading(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "log.md").write_text("# Directory Update Log\n\n## June 17\n* Update\n", encoding="utf-8")

    result = validate_bundle(bundle, require_root_files=False)

    assert result["status"] == "failed"
    assert any("log heading must use YYYY-MM-DD" in error for error in result["errors"])


def test_validate_bundle_accepts_crlf_frontmatter(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "concept.md").write_bytes(
        b"---\r\ntype: Reference\r\ntitle: CRLF\r\n---\r\n\r\nBody\r\n"
    )

    result = validate_bundle(bundle, require_root_files=False)

    assert result["status"] == "passed"


def test_validate_bundle_requires_root_reserved_files_when_requested(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "concept.md").write_text("---\ntype: Reference\n---\n\nBody\n", encoding="utf-8")

    result = validate_bundle(bundle, require_root_files=True)

    assert result["status"] == "failed"
    assert any("index.md is required" in error for error in result["errors"])
    assert any("log.md is required" in error for error in result["errors"])


def test_validate_bundle_requires_root_okf_version_when_requested(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "index.md").write_text("# OKF Index\n", encoding="utf-8")
    (bundle / "log.md").write_text("# Directory Update Log\n\n## 2026-06-17\n* Update\n", encoding="utf-8")
    (bundle / "concept.md").write_text("---\ntype: Reference\n---\n\nBody\n", encoding="utf-8")

    result = validate_bundle(bundle, require_root_files=True)

    assert result["status"] == "failed"
    assert any('root index okf_version must be "0.1"' in error for error in result["errors"])


def test_validate_bundle_rejects_stale_generated_index(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "index.md").write_text('---\nokf_version: "0.1"\n---\n\n# OKF Index\n', encoding="utf-8")
    (bundle / "log.md").write_text("# Directory Update Log\n\n## 2026-06-17\n* Update\n", encoding="utf-8")
    (bundle / "concept.md").write_text(
        "---\ntype: Reference\ntitle: Concept\ndescription: Current concept.\n---\n\nBody\n",
        encoding="utf-8",
    )

    result = validate_bundle(bundle)

    assert result["status"] == "failed"
    assert any("index is stale" in error for error in result["errors"])


def test_build_index_text_groups_concepts_and_subdirectories(tmp_path):
    bundle = tmp_path / "okf"
    concepts = bundle / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "runner.md").write_text(
        (
            "---\n"
            "type: Component\n"
            "title: Runner\n"
            "description: Executes workflows.\n"
            "---\n\n"
            "Body\n"
        ),
        encoding="utf-8",
    )

    text = build_index_text(bundle, bundle)

    assert "* [concepts](concepts/) - OKF concepts in `concepts/`." in text


def test_repo_okf_bundle_is_conformant():
    result = validate_bundle(Path("docs/okf"))

    assert result["status"] == "passed"
    assert result["concept_count"] >= 5
    assert result["warnings"] == []


def test_okf_automation_is_wired_for_agents_hooks_and_ci():
    manifest = json.loads(Path(".agents/config/agent_command_manifest.json").read_text(encoding="utf-8"))
    hook = Path(".githooks/pre-commit").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    skill = Path(".agents/skills/rpa-harness-automation-builder/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "okf_validate" in manifest["commands"]
    assert "okf_generate_indexes" in manifest["commands"]
    assert "scripts/okf.py validate docs/okf" in hook
    assert "docs/okf" in agents
    assert "python scripts/okf.py validate docs/okf" in ci
    assert "python scripts/okf.py generate-indexes docs/okf" in skill
