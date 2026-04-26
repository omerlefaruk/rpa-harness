"""
Persistent memory system for RPA harness.
Adapted from claude-mem: SQLite + FTS5, 3-layer search, hooks, compression.
"""

from harness.memory.engine import RPAMemory
from harness.memory.database import MemoryDatabase
from harness.memory.hooks import MemoryHooks
from harness.memory.search import MemorySearch
from harness.memory.inject import ContextInjector
from harness.memory.compress import MemoryCompressor

__all__ = [
    "RPAMemory",
    "MemoryDatabase",
    "MemoryHooks",
    "MemorySearch",
    "ContextInjector",
    "MemoryCompressor",
]
