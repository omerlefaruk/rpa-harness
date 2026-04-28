"""
Typed RPA Memory event payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryObservation:
    content_session_id: str
    tool_name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_response: Any = None
    cwd: str = ""
    platform_source: str = "rpa-harness"
    tool_use_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None


@dataclass
class ManualMemory:
    text: str
    title: str | None = None
    project: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
