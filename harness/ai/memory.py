"""
Agent short-term memory — maintains step history, successful patterns,
and context within a single agent session.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MemoryEntry:
    id: str
    step_name: str
    action: str
    tool_used: Optional[str]
    tool_args: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    success: bool = True
    error: Optional[str] = None
    selector_used: Optional[str] = None
    selector_healed: Optional[str] = None
    duration_ms: float = 0.0
    screenshot_path: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "step_name": self.step_name,
            "action": self.action,
            "tool_used": self.tool_used,
            "tool_args": self.tool_args,
            "success": self.success,
            "error": self.error,
            "selector_used": self.selector_used,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class AgentMemory:
    def __init__(self, max_history: int = 50):
        self._entries: List[MemoryEntry] = []
        self._selectors: Dict[str, str] = {}
        self._patterns: Dict[str, int] = {}
        self._max_history = max_history
        self._entry_counter = 0

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        self._entry_counter += 1
        entry.id = str(self._entry_counter)
        self._entries.append(entry)

        if len(self._entries) > self._max_history:
            self._entries.pop(0)

        if entry.success and entry.selector_used:
            self._selectors[entry.step_name] = entry.selector_used
        elif entry.selector_healed:
            self._selectors[entry.step_name] = entry.selector_healed

        return entry

    def get_last(self, n: int = 5) -> List[MemoryEntry]:
        return self._entries[-n:]

    def get_successful(self) -> List[MemoryEntry]:
        return [e for e in self._entries if e.success]

    def get_failures(self) -> List[MemoryEntry]:
        return [e for e in self._entries if not e.success]

    def get_selector(self, step_name: str) -> Optional[str]:
        return self._selectors.get(step_name)

    def get_context_for_prompt(self, max_entries: int = 10) -> str:
        recent = self._entries[-max_entries:]
        if not recent:
            return "No previous steps."

        lines = []
        for i, entry in enumerate(recent, 1):
            status = "✓" if entry.success else "✗"
            duration = f" ({entry.duration_ms:.0f}ms)" if entry.duration_ms else ""
            error = f" — {entry.error}" if entry.error else ""
            lines.append(
                f"{status} Step {i}: {entry.step_name}{duration}{error}"
            )

        return "\n".join(lines)

    def summarize(self) -> Dict[str, Any]:
        successful = self.get_successful()
        failures = self.get_failures()

        return {
            "total_steps": len(self._entries),
            "success_count": len(successful),
            "failure_count": len(failures),
            "learned_selectors": dict(self._selectors),
            "last_step": self._entries[-1].step_name if self._entries else None,
            "total_duration_ms": sum(e.duration_ms for e in self._entries),
        }

    def clear(self):
        self._entries.clear()
        self._selectors.clear()
        self._entry_counter = 0
