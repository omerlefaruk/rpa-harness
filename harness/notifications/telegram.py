"""Telegram bot notification channel.

The bot token and chat identifiers are secrets/configuration. They are read
from environment variables and are never written to reports or logs.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from harness.security import redact_text, redact_value

TELEGRAM_API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


@dataclass
class TelegramNotificationConfig:
    enabled: bool = False
    bot_token: str | None = None
    chat_id: str | None = None
    message_thread_id: int | None = None
    topic_threads: dict[str, int] | None = None
    request_timeout_seconds: float = 10.0
    strict: bool = False

    @classmethod
    def from_env(cls) -> TelegramNotificationConfig:
        return cls(
            enabled=_env_bool("RPA_TELEGRAM_ENABLED"),
            bot_token=os.getenv("RPA_TELEGRAM_BOT_TOKEN") or None,
            chat_id=os.getenv("RPA_TELEGRAM_CHAT_ID") or None,
            message_thread_id=_env_int("RPA_TELEGRAM_THREAD_ID"),
            topic_threads=_topic_threads_from_env(),
            request_timeout_seconds=float(os.getenv("RPA_TELEGRAM_TIMEOUT_SECONDS", "10")),
            strict=_env_bool("RPA_TELEGRAM_STRICT"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


class TelegramNotificationError(RuntimeError):
    """Raised when Telegram delivery fails in strict mode or direct CLI usage."""


class TelegramBotChannel:
    def __init__(
        self,
        config: TelegramNotificationConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.config = config or TelegramNotificationConfig.from_env()
        self._client = client

    async def send_message(
        self,
        text: str,
        *,
        topic: str | None = None,
        disable_web_page_preview: bool = True,
        strict: bool | None = None,
    ) -> dict[str, Any] | None:
        if not self.config.configured:
            return self._handle_unconfigured(strict)

        safe_text = self._sanitize_message(text)
        payload: dict[str, Any] = {
            "chat_id": self.config.chat_id,
            "text": safe_text[:MAX_MESSAGE_LENGTH],
            "disable_web_page_preview": disable_web_page_preview,
        }
        thread_id = self._resolve_thread_id(topic, strict)
        if thread_id is not None:
            payload["message_thread_id"] = thread_id

        return await self._post("sendMessage", payload, strict=strict)

    async def ask_question(
        self,
        question: str,
        context: str | None = None,
        *,
        topic: str = "questions",
        strict: bool | None = None,
    ) -> dict[str, Any] | None:
        parts = ["Hey, I need a call on this.", "", question.strip()]
        if context:
            parts.extend(["", f"Context: {context.strip()}"])
        return await self.send_message("\n".join(parts), topic=topic, strict=strict)

    async def send_frustration_report(
        self,
        source: str,
        frustrations: Iterable[str],
        *,
        topic: str = "rants",
        strict: bool | None = None,
    ) -> dict[str, Any] | None:
        items = [item.strip() for item in frustrations if item and item.strip()]
        if not items:
            items = ["I hit friction, but no details were attached."]
        lines = [f"{source}: I got annoyed here.", ""]
        lines.extend(f"- {item}" for item in items)
        lines.append("")
        lines.append("I can keep going, but this is the part slowing me down.")
        return await self.send_message("\n".join(lines), topic=topic, strict=strict)

    async def send_run_report(
        self,
        *,
        suite_name: str,
        summary: dict[str, Any],
        report_paths: dict[str, str] | None = None,
        topic: str = "reports",
    ) -> dict[str, Any] | None:
        tests = summary.get("tests") or {}
        workflows = summary.get("workflows") or {}
        failed_tests = tests.get("failed", 0)
        failed_records = workflows.get("failed_records", 0)
        if failed_tests or failed_records:
            opener = f"Heads up, {suite_name} needs attention."
        else:
            opener = f"{suite_name} is done."
        lines = [
            opener,
            "",
            f"Tests: {tests.get('passed', 0)}/{tests.get('total', 0)} passed",
        ]
        if workflows:
            lines.append(
                "Workflows: "
                f"{workflows.get('processed_records', 0)} records processed, "
                f"{workflows.get('failed_records', 0)} failed"
            )
        lines.append(f"Duration: {summary.get('total_duration_ms', 0)} ms")

        if report_paths:
            lines.extend(["", "Reports:"])
            for fmt, path in sorted(report_paths.items()):
                lines.append(f"- {fmt}: {path}")

        return await self.send_message("\n".join(lines), topic=topic)

    async def send_agent_report(
        self,
        result: dict[str, Any],
        *,
        topic: str = "reports",
    ) -> dict[str, Any] | None:
        status = result.get("status", "unknown")
        opener = (
            "Agent run finished."
            if status in {"success", "passed"}
            else "Agent run needs attention."
        )
        lines = [
            opener,
            "",
            f"Status: {status}",
            f"Steps: {result.get('successful_steps', 0)}/{result.get('total_steps', 0)} passed",
            f"Duration: {result.get('duration_seconds', 0)}s",
        ]
        if result.get("task"):
            lines.extend(["", f"Task: {result['task']}"])
        if result.get("error"):
            lines.extend(["", f"Error: {result['error']}"])
        return await self.send_message("\n".join(lines), topic=topic)

    async def discover_chat_id(self, *, strict: bool | None = None) -> dict[str, Any] | None:
        if not self.config.bot_token:
            return self._handle_missing_token(strict)

        response = await self._post("getUpdates", {}, strict=strict)
        if not response:
            return None

        chats: list[dict[str, Any]] = []
        for update in response.get("result", []):
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat")
            if chat and chat not in chats:
                chats.append(chat)
        return {"ok": True, "chats": redact_value(chats, [self.config.bot_token])}

    def _sanitize_message(self, text: str) -> str:
        return redact_text(text, secret_values=[self.config.bot_token or ""]).strip()

    def _resolve_thread_id(self, topic: str | None, strict: bool | None) -> int | None:
        if not topic:
            return self.config.message_thread_id
        normalized = topic.strip().lower().replace("-", "_")
        thread_id = (self.config.topic_threads or {}).get(normalized)
        if thread_id is not None:
            return thread_id
        return self.config.message_thread_id

    async def _post(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        strict: bool | None = None,
    ) -> dict[str, Any] | None:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.request_timeout_seconds)
        try:
            url = f"{TELEGRAM_API_BASE}/bot{self.config.bot_token}/{method}"
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok", False):
                raise TelegramNotificationError(
                    f"Telegram {method} returned ok=false: {data.get('description', 'unknown')}"
                )
            return data
        except Exception as exc:
            should_raise = self.config.strict if strict is None else strict
            if should_raise:
                raise TelegramNotificationError(
                    f"Telegram {method} failed: {redact_text(exc, [self.config.bot_token or ''])}"
                ) from exc
            return None
        finally:
            if owns_client:
                await client.aclose()

    def _handle_unconfigured(self, strict: bool | None) -> dict[str, Any] | None:
        should_raise = self.config.strict if strict is None else strict
        if should_raise:
            raise TelegramNotificationError(
                "Telegram notifications need RPA_TELEGRAM_BOT_TOKEN and RPA_TELEGRAM_CHAT_ID."
            )
        return None

    def _handle_missing_token(self, strict: bool | None) -> dict[str, Any] | None:
        should_raise = self.config.strict if strict is None else strict
        if should_raise:
            raise TelegramNotificationError("Telegram bot access needs RPA_TELEGRAM_BOT_TOKEN.")
        return None


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    return int(value)


def _topic_threads_from_env() -> dict[str, int]:
    prefix = "RPA_TELEGRAM_TOPIC_"
    topics: dict[str, int] = {}
    for key, value in os.environ.items():
        if not key.startswith(prefix) or not value:
            continue
        topic = key[len(prefix) :].strip().lower()
        if not topic:
            continue
        topics[topic] = int(value)
    return topics
