"""Human-readable bot notifications for RPA runs."""

from __future__ import annotations

import os
from typing import Any

from harness.logger import HarnessLogger
from harness.notifications.telegram import TelegramBotChannel, TelegramNotificationConfig
from harness.security import is_sensitive_key, redact_mapping, redacted_preview

SAFE_CONTEXT_KEYS = {
    "action",
    "attempt",
    "attempts",
    "failure_report",
    "fallback",
    "source",
    "status",
    "step",
    "steps_completed",
    "tool",
    "wait_ms",
    "workflow",
}


class BotNotifier:
    def __init__(
        self,
        *,
        channel: TelegramBotChannel | None = None,
        config: TelegramNotificationConfig | None = None,
        secret_values: list[str] | None = None,
        source: str = "rpa-harness",
    ):
        self.source = source
        self.logger = HarnessLogger("notifications.bot")
        self.config = config or self._config_from_env()
        self.channel = channel or TelegramBotChannel(self.config)
        self._secret_values = self._collect_secret_values(secret_values)

    @classmethod
    def from_env(
        cls,
        *,
        source: str = "rpa-harness",
        secret_values: list[str] | None = None,
    ) -> BotNotifier:
        return cls(source=source, secret_values=secret_values)

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self.config.configured

    async def question(self, question: str, *, context: dict[str, Any] | None = None):
        if not self.enabled:
            return None
        context_text = self._context_items(context)
        return await self._deliver(
            self.channel.ask_question(
                question,
                context=context_text or f"source={self.source}",
                topic="questions",
            ),
            action="question",
        )

    async def failure(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        topic: str = "failures",
    ):
        if not self.enabled:
            return None
        lines = [
            f"{self.source}: this needs attention.",
            "",
            message.strip(),
        ]
        context_text = self._context_text(context)
        if context_text:
            lines.extend(["", context_text])
        return await self._deliver(
            self.channel.send_message("\n".join(lines), topic=topic),
            action="failure",
        )

    async def frustration(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ):
        if not self.enabled:
            return None
        items = [message.strip()]
        context_text = self._context_text(context)
        if context_text:
            items.append(context_text)
        return await self._deliver(
            self.channel.send_frustration_report(self.source, items, topic="rants"),
            action="frustration",
        )

    async def memory_note(self, message: str, *, context: dict[str, Any] | None = None):
        if not self.enabled:
            return None
        lines = [f"{self.source}: memory note.", "", message.strip()]
        context_text = self._context_text(context)
        if context_text:
            lines.extend(["", context_text])
        return await self._deliver(
            self.channel.send_message("\n".join(lines), topic="memories"),
            action="memory_note",
        )

    async def _deliver(self, awaitable, *, action: str):
        try:
            return await awaitable
        except Exception as exc:
            self.logger.warning(f"Telegram {action} notification failed: {exc}")
            return None

    def add_secret_values(self, values) -> None:
        self._secret_values = self._collect_secret_values(
            [*self._secret_values, *list(values or [])]
        )

    def _config_from_env(self) -> TelegramNotificationConfig:
        try:
            return TelegramNotificationConfig.from_env()
        except (TypeError, ValueError) as exc:
            if os.getenv("RPA_TELEGRAM_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}:
                raise
            self.logger.warning(f"Telegram notification config ignored: {exc}")
            return TelegramNotificationConfig(enabled=False)

    def _context_text(self, context: dict[str, Any] | None) -> str:
        items = self._context_items(context)
        return f"Context: {items}" if items else ""

    def _context_items(self, context: dict[str, Any] | None) -> str:
        if not context:
            return ""
        secret_values = sorted(
            dict.fromkeys([self.config.bot_token or "", *self._secret_values]),
            key=len,
            reverse=True,
        )
        redacted = redact_mapping(
            {str(key): value for key, value in context.items() if value not in (None, "")},
            secret_values=secret_values,
        )
        safe = {
            key: self._safe_context_value(key, value, secret_values)
            for key, value in redacted.items()
        }
        if not safe:
            return ""
        return ", ".join(f"{key}={value}" for key, value in safe.items())

    def _safe_context_value(self, key: str, value: Any, secret_values: list[str]) -> str:
        if is_sensitive_key(key):
            return "[REDACTED]"
        if key not in SAFE_CONTEXT_KEYS:
            return "[redacted]"
        return redacted_preview(value, secret_values=secret_values, max_chars=300)

    @staticmethod
    def _collect_secret_values(extra_values: list[str] | None = None) -> list[str]:
        values: list[str] = []
        for key, value in os.environ.items():
            if value and is_sensitive_key(key):
                values.append(value)
        values.extend(str(value) for value in extra_values or [] if value)
        return sorted(dict.fromkeys(values), key=len, reverse=True)
