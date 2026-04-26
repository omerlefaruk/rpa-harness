"""
Structured logging for the RPA harness.
Supports plain text, JSONL, and correlation IDs for tracing.
"""

import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class HarnessLogger:
    _file_handler: Optional[logging.FileHandler] = None
    _jsonl_path: Optional[Path] = None

    def __init__(self, name: str = "rpa-harness", level: str = "INFO",
                 jsonl_output: bool = False, jsonl_path: Optional[str] = None,
                 correlation_id: Optional[str] = None):
        self.name = name
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self._jsonl_output = jsonl_output

        self.logger = logging.getLogger(f"rpa.{name}")
        self.logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | [%(cid)s] %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

            if jsonl_output:
                self._setup_jsonl(jsonl_path or "./logs/harness.jsonl")

        self.logger = logging.LoggerAdapter(self.logger, {"cid": self.correlation_id})

    def _setup_jsonl(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = p
        handler = logging.FileHandler(str(p))
        handler.setFormatter(JsonlFormatter(self.correlation_id))
        handler.setLevel(getattr(logging, "DEBUG"))
        self.logger.logger.addHandler(handler)

    def info(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.info(self._enrich(msg, extra))

    def debug(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.debug(self._enrich(msg, extra))

    def warning(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.warning(self._enrich(msg, extra))

    def error(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.error(self._enrich(msg, extra))

    def critical(self, msg: str, extra: Optional[Dict[str, Any]] = None):
        self.logger.critical(self._enrich(msg, extra))

    def step(self, step_number: int, step_name: str, **kwargs):
        extra = {"step": step_number, "step_name": step_name, **kwargs}
        self.info(f"Step {step_number}: {step_name}", extra=extra)

    def step_result(self, step_number: int, success: bool, duration_ms: float,
                    details: Optional[Dict[str, Any]] = None):
        extra = {
            "step": step_number,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            **(details or {}),
        }
        status = "PASS" if success else "FAIL"
        self.info(f"  [{status}] Step {step_number} ({duration_ms:.0f}ms)", extra=extra)

    def observation(self, step_name: str, selector: Optional[str] = None,
                    success: bool = True, duration_ms: float = 0,
                    error: Optional[str] = None, **kwargs):
        extra = {
            "type": "observation",
            "step": step_name,
            "selector": selector,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "error": error,
            **kwargs,
        }
        if success:
            self.info(f"Observed: {step_name}", extra=extra)
        else:
            self.warning(f"Observation failed: {step_name} — {error}", extra=extra)

    def _enrich(self, msg: str, extra: Optional[dict] = None) -> str:
        if self._jsonl_output and extra:
            return f"{msg} | {json.dumps(extra, default=str)}"
        return msg


class JsonlFormatter(logging.Formatter):
    def __init__(self, correlation_id: str):
        super().__init__()
        self.correlation_id = correlation_id

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "correlation_id": self.correlation_id,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])
        return json.dumps(entry, default=str)
