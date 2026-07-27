import subprocess
from pathlib import Path

TEXT_EXTENSIONS = {".py", ".sh", ".md", ".yaml", ".yml", ".toml", ".txt", ".json", ".html"}
TEXT_NAMES = {".gitignore", ".gitattributes"}


def iter_text_files(repo: Path):
    try:
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=repo,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.splitlines()
    except (FileNotFoundError, subprocess.CalledProcessError):
        ignored_dirs = {
            ".git",
            ".pytest_cache",
            ".pytest_tmp",
            "__pycache__",
            "reports",
            "downloads",
            "screenshots",
            "playwright-report",
            "test-results",
        }
        for path in repo.rglob("*"):
            if any(part in ignored_dirs for part in path.relative_to(repo).parts):
                continue
            if path.is_file() and (path.suffix in TEXT_EXTENSIONS or path.name in TEXT_NAMES):
                yield path
        return

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
