from pathlib import Path


def test_pyproject_readme_target_exists():
    repo = Path(__file__).resolve().parents[1]
    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert 'readme = "README.md"' in pyproject
    assert (repo / "README.md").exists()
