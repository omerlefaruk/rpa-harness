"""Tests for human-readable bot notifications."""

from __future__ import annotations

import pytest

from harness.notifications.bot import BotNotifier
from harness.notifications.telegram import TelegramNotificationConfig


class FakeTelegramChannel:
    def __init__(self):
        self.calls: list[tuple[str, str, str | None]] = []

    async def ask_question(self, question, *, context=None, topic="questions"):
        self.calls.append(("question", question + "\n" + (context or ""), topic))
        return {"ok": True}

    async def send_message(self, text, *, topic=None):
        self.calls.append(("message", text, topic))
        return {"ok": True}

    async def send_frustration_report(self, source, frustrations, *, topic="rants"):
        self.calls.append(("frustration", source + "\n" + "\n".join(frustrations), topic))
        return {"ok": True}


@pytest.mark.asyncio
async def test_bot_notifier_skips_when_disabled():
    channel = FakeTelegramChannel()
    notifier = BotNotifier(
        channel=channel,
        config=TelegramNotificationConfig(enabled=False),
        source="test",
    )

    result = await notifier.failure("failed")

    assert result is None
    assert channel.calls == []


@pytest.mark.asyncio
async def test_bot_notifier_routes_failure_and_redacts_context():
    channel = FakeTelegramChannel()
    notifier = BotNotifier(
        channel=channel,
        config=TelegramNotificationConfig(
            enabled=True,
            bot_token="123456:secret-token",
            chat_id="chat",
        ),
        source="workflow.invoice",
    )

    result = await notifier.failure(
        "Could not finish record.",
        context={"record_id": "INV-1", "token": "123456:secret-token"},
    )

    assert result == {"ok": True}
    assert channel.calls == [
        (
            "message",
            "workflow.invoice: this needs attention.\n\n"
            "Could not finish record.\n\n"
            "Context: record_id=[redacted], token=[REDACTED]",
            "failures",
        )
    ]


@pytest.mark.asyncio
async def test_bot_notifier_delivery_failure_does_not_escape_automatic_hook():
    class BrokenChannel:
        async def send_message(self, text, *, topic=None):
            raise RuntimeError("telegram down")

    notifier = BotNotifier(
        channel=BrokenChannel(),
        config=TelegramNotificationConfig(
            enabled=True,
            bot_token="token",
            chat_id="chat",
            strict=True,
        ),
        source="workflow.invoice",
    )

    result = await notifier.failure("Could not finish record.")

    assert result is None


@pytest.mark.asyncio
async def test_bot_notifier_routes_questions_and_frustration():
    channel = FakeTelegramChannel()
    config = TelegramNotificationConfig(enabled=True, bot_token="token", chat_id="chat")
    notifier = BotNotifier(channel=channel, config=config, source="yaml-runner")

    await notifier.question("Retry?", context={"step": "login"})
    await notifier.frustration("Retrying step", context={"attempt": 2})
    await notifier.memory_note("Saved summary", context={"workflow": "demo"})

    assert channel.calls[0] == (
        "question",
        "Retry?\nstep=login",
        "questions",
    )
    assert channel.calls[1] == (
        "frustration",
        "yaml-runner\nRetrying step\nContext: attempt=2",
        "rants",
    )
    assert channel.calls[2] == (
        "message",
        "yaml-runner: memory note.\n\nSaved summary\n\nContext: workflow=demo",
        "memories",
    )


def test_bot_notifier_ignores_bad_optional_env_config(monkeypatch):
    monkeypatch.setenv("RPA_TELEGRAM_TOPIC_MEMORIES", "not-a-number")

    notifier = BotNotifier.from_env(source="workflow.bad-env")

    assert notifier.enabled is False


def test_bot_notifier_redacts_neutral_context_values_from_secret_values():
    notifier = BotNotifier(
        channel=FakeTelegramChannel(),
        config=TelegramNotificationConfig(
            enabled=True,
            bot_token="token",
            chat_id="chat",
        ),
        source="workflow.invoice",
        secret_values=["super-secret-token"],
    )

    assert (
        notifier._context_items({"error": "server echoed super-secret-token"})
        == "error=[redacted]"
    )


def test_bot_notifier_strict_bad_env_config_raises(monkeypatch):
    monkeypatch.setenv("RPA_TELEGRAM_STRICT", "true")
    monkeypatch.setenv("RPA_TELEGRAM_TOPIC_MEMORIES", "not-a-number")

    with pytest.raises(ValueError):
        BotNotifier.from_env(source="workflow.bad-env")
