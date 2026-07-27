"""Canonical ActiveGraph agent knowledge surface contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"


def test_exactly_one_canonical_authoring_skill():
    builder = (SKILLS / "rpa-harness-automation-builder" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "only** canonical skill" in builder or "only canonical" in builder.lower()
    assert "AutomationApplication" in builder
    for stage in (
        "Intent",
        "Discovery",
        "Proposal",
        "Validation",
        "Approval",
        "Execution",
        "Verification",
        "Reconciliation",
        "Repair",
        "Promotion",
    ):
        assert stage.lower() in builder.lower()


def test_thin_skills_point_to_canonical_and_avoid_yaml_runtime():
    for name in (
        "selector-strategies",
        "error-recovery",
        "excel-workflows",
        "playwright-automation",
        "windows-ui-automation",
        "search-to-rpa-workflow",
    ):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert "rpa-harness-automation-builder" in text
        assert "yaml_runner" not in text
        assert "--run-yaml" not in text


def test_selector_guidance_matches_executable_priority():
    text = (SKILLS / "selector-strategies" / "SKILL.md").read_text(encoding="utf-8")
    assert "role" in text
    assert "automation_id" in text
    from harness.automation.capabilities import (
        BROWSER_SELECTOR_PRIORITY,
        DESKTOP_SELECTOR_PRIORITY,
    )

    assert BROWSER_SELECTOR_PRIORITY[0] == "role"
    assert DESKTOP_SELECTOR_PRIORITY[0] == "automation_id"


def test_failure_guidance_uses_executable_terminal_states():
    text = (SKILLS / "error-recovery" / "SKILL.md").read_text(encoding="utf-8")
    for state in (
        "completed",
        "failed",
        "blocked",
        "needs_reconciliation",
        "rejected",
        "cancelled",
    ):
        assert state in text
