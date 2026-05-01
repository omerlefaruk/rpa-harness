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
        ".autoresearch/worktrees/",
        ".autoresearch/supervisor.jsonl",
        ".autoresearch/tech_radar.state.json",
        ".autoresearch/tech_radar.jsonl",
        ".autoresearch/tech_radar_candidates.md",
        ".autoresearch/autoresearch.jsonl",
        ".autoresearch/autoresearch_dashboard.html",
        ".autoresearch/codex_prompt.md",
        ".pytest_tmp/",
    }

    assert required_patterns.issubset(patterns)
