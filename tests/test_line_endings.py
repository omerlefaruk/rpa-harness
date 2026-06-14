import subprocess
from pathlib import Path

TEXT_EXTENSIONS = {".py", ".sh", ".md", ".yaml", ".yml", ".toml", ".txt", ".json", ".html"}
TEXT_NAMES = {".gitignore", ".gitattributes"}


def iter_text_files(repo: Path):
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    for relative_path in tracked:
        path = repo / relative_path
        if path.is_file() and (path.suffix in TEXT_EXTENSIONS or path.name in TEXT_NAMES):
            yield path


def test_repository_text_files_use_lf_line_endings():
    repo = Path(__file__).resolve().parents[1]
    offenders = []
    for path in iter_text_files(repo):
        data = path.read_bytes()
        if b"\r" in data:
            offenders.append(str(path.relative_to(repo)))
    assert offenders == []
