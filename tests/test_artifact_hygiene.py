"""Guards for generated artifact hygiene."""

from pathlib import Path


def test_generated_artifact_paths_are_ignored_by_default():
    repo = Path(__file__).resolve().parents[1]
    patterns = set((repo / ".gitignore").read_text(encoding="utf-8").splitlines())

    required_patterns = {
        "reports/",
        "runs/*",
        "!runs/.gitkeep",
        "screenshots/",
        "downloads/",
        "logs/",
        "data/*.xlsx",
        "data/*.csv",
        "data/*.db",
        "data/*.db-*",
        "data/*.sqlite",
        "data/*.sqlite-*",
        ".env",
        ".env.local",
        "playwright-report/",
        "test-results/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".autoresearch/worktrees/",
        ".autoresearch/supervisor.jsonl",
        ".autoresearch/supervisor_plan.md",
        ".autoresearch/review.md",
        ".autoresearch/review.json",
        ".autoresearch/autoresearch.learnings.md",
    }

    assert required_patterns.issubset(patterns)
