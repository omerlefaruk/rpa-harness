"""Live operator checkpoints for copilot-style workflow runs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from harness.core.artifacts import append_jsonl
from harness.core.time import utc_now_iso
from harness.security import redact_text, sanitize_url


class CopilotCheckpoint:
    def __init__(
        self,
        run_dir: str | Path,
        *,
        input_func: Callable[[str], str] | None = None,
    ):
        self.run_dir = Path(run_dir)
        self.input_func = input_func or input

    async def ask(
        self,
        *,
        workflow: dict[str, Any],
        step: dict[str, Any],
        reason: str,
        run_id: str | None = None,
        drivers: dict[str, Any] | None = None,
        secret_values: list[str] | None = None,
        question: str | None = None,
        choices: list[str] | None = None,
    ) -> dict[str, Any]:
        choices = choices or ["continue", "stop"]
        question_id = f"q-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        artifacts = await self._capture_artifacts(question_id, drivers or {}, secret_values or [])
        prompt = question or f"Continue before step '{step.get('id')}'?"
        record = {
            "schema_version": 1,
            "question_id": question_id,
            "run_id": run_id,
            "workflow": workflow.get("id"),
            "step_id": step.get("id"),
            "reason": reason,
            "question": prompt,
            "choices": choices,
            "default": choices[0],
            "artifacts": artifacts,
            "created_at": utc_now_iso(),
        }
        self.run_dir.mkdir(parents=True, exist_ok=True)
        append_jsonl(self.run_dir / "questions.jsonl", record)

        print(f"\nCopilot question [{question_id}]")
        print(prompt)
        print(f"Choices: {', '.join(choices)}")
        answer = (await asyncio.to_thread(self.input_func, f"{choices[0]}> ")).strip()
        if not answer:
            answer = choices[0]
        action = "stop" if answer.lower() in {"stop", "abort", "quit", "no"} else "continue"
        result = {
            "question_id": question_id,
            "action": action,
            "answer": answer,
            "answered_at": utc_now_iso(),
            "artifacts": artifacts,
        }
        append_jsonl(self.run_dir / "answers.jsonl", result)
        return result

    async def _capture_artifacts(
        self,
        question_id: str,
        drivers: dict[str, Any],
        secret_values: list[str],
    ) -> dict[str, Any]:
        browser = drivers.get("browser")
        page = getattr(browser, "page", None)
        if not page:
            return {}

        artifact_dir = self.run_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, Any] = {"current_url": sanitize_url(getattr(page, "url", ""))}
        screenshot_path = artifact_dir / f"{question_id}.png"
        dom_path = artifact_dir / f"{question_id}.dom.html"
        try:
            await page.screenshot(path=str(screenshot_path))
            artifacts["screenshot"] = str(screenshot_path.relative_to(self.run_dir))
        except Exception as exc:
            artifacts["screenshot_error"] = redact_text(str(exc), secret_values)
        try:
            dom = await page.content()
            dom_path.write_text(redact_text(dom, secret_values), encoding="utf-8")
            artifacts["dom_snapshot"] = str(dom_path.relative_to(self.run_dir))
        except Exception as exc:
            artifacts["dom_snapshot_error"] = redact_text(str(exc), secret_values)
        return artifacts
