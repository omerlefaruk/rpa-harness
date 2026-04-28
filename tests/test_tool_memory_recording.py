"""Tests for automatic agent tool-call memory recording."""

from __future__ import annotations

import json

import pytest

from harness.ai.tools import Tool, ToolRegistry
from harness.memory.config import MemoryConfig


class FakeMemoryRecorder:
    def __init__(self, required: bool = False):
        self.config = MemoryConfig(enabled=True, required=required)
        self.calls: list[dict] = []

    async def record_observation(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "stored", "id": len(self.calls)}


@pytest.mark.asyncio
async def test_tool_registry_records_successful_low_level_tool_call_to_memory(capsys):
    recorder = FakeMemoryRecorder()
    registry = ToolRegistry(memory_recorder=recorder, memory_session_id="agent-1")

    async def handler(selector: str, password: str):
        return {"status": "ok", "token": "secret-response-token"}

    registry.register(
        Tool(
            name="browser_fill",
            description="Fill field",
            parameters={},
            handler=handler,
            category="browser",
        )
    )

    result = await registry.execute(
        "browser_fill",
        {"selector": "#password", "password": "super-secret-password"},
    )
    logs = capsys.readouterr().out

    assert result["status"] == "ok"
    assert len(recorder.calls) == 1

    call = recorder.calls[0]
    serialized = json.dumps(call, sort_keys=True)
    assert call["content_session_id"] == "agent-1"
    assert call["tool_name"] == "tool_call.browser_fill"
    assert call["tool_input"]["tool"] == "browser_fill"
    assert call["tool_input"]["selector"] == "#password"
    assert call["tool_response"]["success"] is True
    assert "duration_ms" in call["tool_response"]
    assert "super-secret-password" not in serialized
    assert "secret-response-token" not in serialized
    assert "[REDACTED]" in serialized
    assert "super-secret-password" not in logs
    assert "password=[REDACTED]" in logs


@pytest.mark.asyncio
async def test_tool_registry_records_failed_tool_call_before_reraising():
    recorder = FakeMemoryRecorder()
    registry = ToolRegistry(memory_recorder=recorder, memory_session_id="agent-1")

    async def handler(url: str):
        raise RuntimeError("request failed token=abc123")

    registry.register(
        Tool(
            name="api_call",
            description="Call API",
            parameters={},
            handler=handler,
            category="api",
        )
    )

    with pytest.raises(RuntimeError):
        await registry.execute("api_call", {"url": "https://example.test/report?token=abc123"})

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    serialized = json.dumps(call, sort_keys=True)
    assert call["tool_name"] == "tool_call.api_call"
    assert call["tool_response"]["success"] is False
    assert "request failed" in call["tool_response"]["error"]
    assert "token=abc123" not in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.asyncio
async def test_tool_registry_does_not_record_memory_tool_calls():
    recorder = FakeMemoryRecorder()
    registry = ToolRegistry(memory_recorder=recorder, memory_session_id="agent-1")

    async def handler(query: str):
        return {"results": []}

    registry.register(
        Tool(
            name="mem_search",
            description="Search memory",
            parameters={},
            handler=handler,
            category="memory",
        )
    )

    await registry.execute("mem_search", {"query": "selector"})

    assert recorder.calls == []
