"""
Configuration for RPA Memory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class MemoryConfig:
    enabled: bool = True
    worker_url: str = "http://127.0.0.1:37777"
    db_path: str = "./data/rpa_memory.db"
    required: bool = False
    project: str = "rpa-harness"
    request_timeout_seconds: float = 2.0
    semantic_inject: bool = False
    semantic_inject_limit: int = 5

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        return cls(
            enabled=_env_bool("RPA_MEMORY_ENABLED", True),
            worker_url=os.getenv("RPA_MEMORY_WORKER_URL", "http://127.0.0.1:37777"),
            db_path=os.getenv("RPA_MEMORY_DB", "./data/rpa_memory.db"),
            required=_env_bool("RPA_MEMORY_REQUIRED", False),
            project=os.getenv("RPA_MEMORY_PROJECT", "rpa-harness"),
            request_timeout_seconds=float(os.getenv("RPA_MEMORY_TIMEOUT", "2")),
            semantic_inject=_env_bool("RPA_MEMORY_SEMANTIC_INJECT", False),
            semantic_inject_limit=int(os.getenv("RPA_MEMORY_SEMANTIC_INJECT_LIMIT", "5")),
        )
