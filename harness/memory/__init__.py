"""
RPA Memory.

Observation-first persistent memory for automation runs, workflows, and
agent sessions. The retrieval contract is search -> timeline -> details.
"""

from harness.memory.client import MemoryClient
from harness.memory.config import MemoryConfig
from harness.memory.errors import MemoryUnavailableError
from harness.memory.events import ManualMemory, MemoryObservation
from harness.memory.recorder import MemoryRecorder
from harness.memory.store import MemoryStore

__all__ = [
    "ManualMemory",
    "MemoryClient",
    "MemoryConfig",
    "MemoryObservation",
    "MemoryRecorder",
    "MemoryStore",
    "MemoryUnavailableError",
]
