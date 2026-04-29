"""Tests for Telegram notification integration."""

import pytest

from harness.notifications.telegram import (
    MAX_MESSAGE_LENGTH,
    TelegramBotChannel,
    TelegramNotificationConfig,
    TelegramNotificationError,
)


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload or {"ok": True, "result": {"message_id": 1}}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, json):
        self.posts.append({"url": url, "json": json})
        return _FakeResponse()


@pytest.mark.asyncio
async def test_send_message_posts_to_telegram_without_leaking_token():
    client = _FakeClient()
    channel = TelegramBotChannel(
        TelegramNotificationConfig(
            enabled=True,
            bot_token="123456:secret-token",
            chat_id="-1001",
            message_thread_id=42,
        ),
        client=client,
    )

    result = await channel.send_message("token=123456:secret-token\nrun finished", strict=True)

    assert result["ok"] is True
    assert client.posts[0]["json"]["chat_id"] == "-1001"
    assert client.posts[0]["json"]["message_thread_id"] == 42
    assert "123456:secret-token" not in client.posts[0]["json"]["text"]


@pytest.mark.asyncio
async def test_send_message_routes_to_named_topic():
    client = _FakeClient()
    channel = TelegramBotChannel(
        TelegramNotificationConfig(
            enabled=True,
            bot_token="token",
            chat_id="-1001",
            topic_threads={"memories": 14},
        ),
        client=client,
    )

    await channel.send_message("Memory updated", topic="memories", strict=True)

    assert client.posts[0]["json"]["message_thread_id"] == 14


@pytest.mark.asyncio
async def test_run_report_formats_summary_and_report_paths():
    client = _FakeClient()
    channel = TelegramBotChannel(
        TelegramNotificationConfig(
            enabled=True,
            bot_token="token",
            chat_id="chat",
            topic_threads={"reports": 9},
        ),
        client=client,
    )

    await channel.send_run_report(
        suite_name="capability-suite",
        summary={
            "tests": {"total": 2, "passed": 1},
            "workflows": {"processed_records": 4, "failed_records": 1},
            "total_duration_ms": 250,
        },
        report_paths={"json": "./reports/report.json"},
    )

    text = client.posts[0]["json"]["text"]
    assert "Heads up, capability-suite needs attention." in text
    assert "Tests: 1/2 passed" in text
    assert "Workflows: 4 records processed, 1 failed" in text
    assert "- json: ./reports/report.json" in text
    assert client.posts[0]["json"]["message_thread_id"] == 9


@pytest.mark.asyncio
async def test_question_and_frustration_messages_have_expected_labels():
    client = _FakeClient()
    channel = TelegramBotChannel(
        TelegramNotificationConfig(
            enabled=True,
            bot_token="token",
            chat_id="chat",
            topic_threads={"questions": 10, "rants": 12},
        ),
        client=client,
    )

    await channel.ask_question("Retry the invoice workflow?", context="source=bot-a")
    await channel.send_frustration_report(
        "bot-a",
        ["Login timeout", "Missing success check"],
    )

    question_text = client.posts[0]["json"]["text"]
    rant_text = client.posts[1]["json"]["text"]
    assert question_text.startswith("Hey, I need a call on this.")
    assert "Retry the invoice workflow?" in question_text
    assert "Context: source=bot-a" in question_text
    assert rant_text.startswith("bot-a: I got annoyed here.")
    assert "- Login timeout" in rant_text
    assert "- Missing success check" in rant_text
    assert "this is the part slowing me down" in rant_text
    assert client.posts[0]["json"]["message_thread_id"] == 10
    assert client.posts[1]["json"]["message_thread_id"] == 12


@pytest.mark.asyncio
async def test_strict_mode_rejects_unknown_topic_mapping():
    client = _FakeClient()
    channel = TelegramBotChannel(
        TelegramNotificationConfig(enabled=True, bot_token="token", chat_id="chat"),
        client=client,
    )

    with pytest.raises(TelegramNotificationError):
        await channel.send_message("hello", topic="missing", strict=True)
    assert client.posts == []


@pytest.mark.asyncio
async def test_missing_config_is_noop_by_default_and_error_in_strict_mode():
    channel = TelegramBotChannel(TelegramNotificationConfig(enabled=True))

    assert await channel.send_message("hello") is None

    with pytest.raises(TelegramNotificationError):
        await channel.send_message("hello", strict=True)


@pytest.mark.asyncio
async def test_long_message_is_clamped_to_telegram_limit():
    client = _FakeClient()
    channel = TelegramBotChannel(
        TelegramNotificationConfig(enabled=True, bot_token="token", chat_id="chat"),
        client=client,
    )

    await channel.send_message("x" * (MAX_MESSAGE_LENGTH + 100), strict=True)

    assert len(client.posts[0]["json"]["text"]) == MAX_MESSAGE_LENGTH
