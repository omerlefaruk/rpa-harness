from pathlib import Path

TEXT_EXTENSIONS = {".py", ".sh", ".md", ".yaml", ".yml", ".toml", ".txt", ".json", ".html"}
TEXT_NAMES = {".gitignore", ".gitattributes"}
CHECK_DIRS = [".autoresearch", "config", "docs", "harness", "scripts", "subagents", "tests", "tools", "workflows"]


def iter_text_files(repo: Path):
    for relative_dir in CHECK_DIRS:
        root = repo / relative_dir
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and (path.suffix in TEXT_EXTENSIONS or path.name in TEXT_NAMES):
                yield path
    for name in ["main.py", "pyproject.toml", "requirements.txt", "README.md", ".gitignore", ".gitattributes"]:
        path = repo / name
        if path.exists():
            yield path


def test_repository_text_files_use_lf_line_endings():
    repo = Path(__file__).resolve().parents[1]
    offenders = []
    for path in iter_text_files(repo):
        data = path.read_bytes()
        if b"\r" in data:
            offenders.append(str(path.relative_to(repo)))
    assert offenders == []
