from __future__ import annotations

import shutil
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path


def init_workspace(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    _copy_tree(files("harness.templates.workspace"), target)
    for folder in ("runs", "reports", "builder_sessions"):
        (target / folder).mkdir(exist_ok=True)


def _copy_tree(source: Traversable, target: Path) -> None:
    for item in source.iterdir():
        if item.name in {"__pycache__", "__init__.py"}:
            continue
        destination = target / item.name
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            _copy_tree(item, destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            with item.open("rb") as src, destination.open("wb") as out:
                shutil.copyfileobj(src, out)
