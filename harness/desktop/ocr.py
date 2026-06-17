"""Command-backed OCR helpers for desktop evidence."""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Iterable

from harness.security import redact_text


class OcrEngine:
    def __init__(self, command: str | list[str] | None):
        self.command = command

    def read_image(
        self,
        image_path: str | Path,
        *,
        secret_values: Iterable[str] | None = None,
        timeout: int = 30,
    ) -> dict:
        if not self.command:
            return {"status": "blocked", "reason": "OCR command is not configured"}
        path = Path(image_path)
        if not path.exists():
            return {"status": "blocked", "reason": f"OCR image does not exist: {path}"}
        args = self._command_args(path)
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        text = redact_text(completed.stdout.strip(), secret_values)
        if completed.returncode != 0:
            return {
                "status": "error",
                "reason": redact_text(completed.stderr.strip(), secret_values),
                "returncode": completed.returncode,
                "image": str(path),
            }
        return {"status": "ok", "text": text, "image": str(path)}

    def wait_for_text(
        self,
        image_path: str | Path,
        expected: str,
        *,
        secret_values: Iterable[str] | None = None,
        timeout: int = 10,
    ) -> dict:
        deadline = time.time() + timeout
        last = {"status": "blocked", "reason": "OCR did not run"}
        while time.time() < deadline:
            last = self.read_image(image_path, secret_values=secret_values, timeout=timeout)
            if expected in str(last.get("text", "")):
                return {**last, "matched": True}
            time.sleep(0.2)
        return {**last, "matched": False}

    def _command_args(self, path: Path) -> list[str]:
        args = list(self.command) if isinstance(self.command, list) else shlex.split(str(self.command))
        if any("{image}" in arg for arg in args):
            return [arg.replace("{image}", str(path)) for arg in args]
        return [*args, str(path)]
