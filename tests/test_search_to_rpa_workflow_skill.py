"""Guards for the search-to-RPA workflow skill."""

from pathlib import Path


def test_search_to_rpa_workflow_skill_exists_and_requires_hardening():
    repo = Path(__file__).resolve().parents[1]
    skill_path = repo / ".agents" / "skills" / "search-to-rpa-workflow" / "SKILL.md"

    text = skill_path.read_text(encoding="utf-8")

    assert "name: search-to-rpa-workflow" in text
    assert "RPA Memory" in text
    assert "dedicated harness artifact" in text
    assert "browser selector swarm" in text
    assert "autoresearch" in text
    assert "python3 tools/autoresearch_runner.py --once" in text
