"""Discoverable, hashed Feature Skills; prose is guidance, never policy."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FeatureSkill:
    name: str
    path: str
    content: str
    content_hash: str
    examples: tuple[str, ...] = ()
    provenance: str = "rpa-harness"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "content": self.content,
            "content_hash": self.content_hash,
            "examples": list(self.examples),
            "provenance": self.provenance,
        }


SKILL_ROOT = Path(__file__).resolve().parents[1] / "feature_skills"


def discover_skills(root: Path | str = SKILL_ROOT) -> tuple[FeatureSkill, ...]:
    base = Path(root)
    if not base.exists():
        return ()
    found: list[FeatureSkill] = []
    for path in sorted(base.glob("*/SKILL.md")):
        content = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        examples = tuple(str(item.relative_to(base)) for item in sorted(path.parent.glob("examples/*")) if item.is_file())
        found.append(FeatureSkill(path.parent.name, str(path.relative_to(base)), content, digest, examples))
    return tuple(found)


def get_skill(name: str, root: Path | str = SKILL_ROOT) -> FeatureSkill:
    for skill in discover_skills(root):
        if skill.name == name:
            return skill
    raise KeyError(f"unknown feature skill: {name}")
