"""Shared identifier helpers."""

from __future__ import annotations

import re

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
WORKFLOW_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def slug_id(value: str) -> str:
    slug = _SAFE_ID_RE.sub("_", value.strip()).strip("_").lower()
    return slug or "workflow"
