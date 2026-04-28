"""Tests for the HTTP-backed RPA memory client contract."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest


def _memory_api():
    from harness.memory import (
        MemoryClient,
        MemoryConfig,
        MemoryRecorder,
        MemoryUnavailableError,
    )

    return MemoryClient, MemoryConfig, MemoryRecorder, MemoryUnavailableError


def _query_params(request: httpx.Request) -> dict[str, str]:
    raw_query = request.url.query.decode()
    return {key: values[-1] for key, values in parse_qs(raw_query).items()}


async def _close_client(client) -> None:
    close = getattr(client, "aclose", None)
    if close:
        await close()


def test_memory_config_accepts_worker_settings():
    _, MemoryConfig, _, _ = _memory_api()

    config = MemoryConfig(
        enabled=True,
        worker_url="http://127.0.0.1:37777",
        required=False,
        project="rpa-harness",
        request_timeout_seconds=1.5,
        semantic_inject=True,
        semantic_inject_limit=3,
    )

    assert config.enabled is True
    assert config.worker_url == "http://127.0.0.1:37777"
    assert config.required is False
    assert config.project == "rpa-harness"
    assert config.request_timeout_seconds == 1.5
    assert config.semantic_inject is True
    assert config.semantic_inject_limit == 3


def test_memory_package_exports_new_api_without_legacy_db_aliases():
    import harness.memory as memory

    assert hasattr(memory, "MemoryClient")
    assert hasattr(memory, "MemoryConfig")
    assert hasattr(memory, "MemoryRecorder")
    assert hasattr(memory, "MemoryUnavailableError")
    assert not hasattr(memory, "MemoryDatabase")
    assert not hasattr(memory, "RPAMemory")


def test_memory_server_imports_and_builds_app_with_current_dependency_stack():
    from harness.memory.server import create_memory_app

    app = create_memory_app(":memory:")

    assert app.title == "RPA Memory"


@pytest.mark.asyncio
async def test_memory_client_search_calls_worker_search_endpoint():
    MemoryClient, MemoryConfig, _, _ = _memory_api()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [{"id": "obs_1", "score": 0.91}]})

    client = MemoryClient(
        config=MemoryConfig(
            enabled=True,
            worker_url="http://127.0.0.1:37777",
            required=True,
            project="rpa-harness",
            request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await client.search(query="submit button", project="rpa-harness", limit=5)
    finally:
        await _close_client(client)

    assert result["results"] == [{"id": "obs_1", "score": 0.91}]
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/search"
    params = _query_params(seen[0])
    assert params["query"] == "submit button"
    assert params["project"] == "rpa-harness"
    assert params["limit"] == "5"


@pytest.mark.asyncio
async def test_memory_client_timeline_calls_worker_timeline_endpoint():
    MemoryClient, MemoryConfig, _, _ = _memory_api()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"observations": [{"id": 10}, {"id": 11}, {"id": 12}]},
        )

    client = MemoryClient(
        config=MemoryConfig(
            enabled=True,
            worker_url="http://127.0.0.1:37777",
            required=True,
            project="rpa-harness",
            request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await client.timeline(
            anchor=11,
            project="rpa-harness",
            depth_before=1,
            depth_after=1,
        )
    finally:
        await _close_client(client)

    assert [observation["id"] for observation in result["observations"]] == [
        10,
        11,
        12,
    ]
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/timeline"
    assert _query_params(seen[0]) == {
        "anchor": "11",
        "project": "rpa-harness",
        "depth_before": "1",
        "depth_after": "1",
    }


@pytest.mark.asyncio
async def test_memory_client_get_observations_batches_ids():
    MemoryClient, MemoryConfig, _, _ = _memory_api()
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"id": 1, "tool_name": "browser.click"},
                    {"id": 2, "tool_name": "browser.expect"},
                ]
            },
        )

    client = MemoryClient(
        config=MemoryConfig(
            enabled=True,
            worker_url="http://127.0.0.1:37777",
            required=True,
            project="rpa-harness",
            request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await client.get_observations([1, 2], project="rpa-harness")
    finally:
        await _close_client(client)

    assert [observation["id"] for observation in result["observations"]] == [1, 2]
    assert seen == [{"ids": [1, 2], "project": "rpa-harness"}]


@pytest.mark.asyncio
async def test_memory_client_optional_mode_returns_unavailable_result():
    MemoryClient, MemoryConfig, _, _ = _memory_api()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("worker is down", request=request)

    client = MemoryClient(
        config=MemoryConfig(
            enabled=True,
            worker_url="http://127.0.0.1:37777",
            required=False,
            project="rpa-harness",
            request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await client.search(query="anything", project="rpa-harness")
    finally:
        await _close_client(client)

    assert result == {
        "available": False,
        "error": "memory worker unavailable",
        "results": [],
    }


@pytest.mark.asyncio
async def test_memory_client_required_mode_raises_memory_unavailable():
    MemoryClient, MemoryConfig, _, MemoryUnavailableError = _memory_api()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("worker is down", request=request)

    client = MemoryClient(
        config=MemoryConfig(
            enabled=True,
            worker_url="http://127.0.0.1:37777",
            required=True,
            project="rpa-harness",
            request_timeout_seconds=1,
        ),
        transport=httpx.MockTransport(handler),
    )

    try:
        with pytest.raises(MemoryUnavailableError):
            await client.search(query="anything", project="rpa-harness")
    finally:
        await _close_client(client)


@pytest.mark.asyncio
async def test_memory_recorder_redacts_observation_payload_before_client_write():
    _, MemoryConfig, MemoryRecorder, _ = _memory_api()
    secret = "fixture-secret-value"

    class FakeMemoryClient:
        def __init__(self):
            self.calls: list[dict] = []

        async def record_observation(self, *args, **kwargs):
            self.calls.append({"args": args, "kwargs": kwargs})
            return {"id": "obs_1", "available": True}

    fake_client = FakeMemoryClient()
    recorder = MemoryRecorder(
        client=fake_client,
        config=MemoryConfig(
            enabled=True,
            worker_url="http://127.0.0.1:37777",
            required=True,
            project="rpa-harness",
            request_timeout_seconds=1,
        ),
    )

    result = await recorder.record_observation(
        content_session_id="session-1",
        tool_name="api.get",
        tool_input={
            "url": "https://example.test/report?token=abc123",
            "headers": {"Authorization": "Bearer abc123"},
            "secret_value": secret,
        },
        tool_response={"status_code": 200, "body": f"token={secret}"},
        cwd="/tmp/rpa-harness",
    )

    serialized = json.dumps(fake_client.calls, sort_keys=True)
    assert result == {"id": "obs_1", "available": True}
    assert secret not in serialized
    assert "Bearer abc123" not in serialized
    assert "token=abc123" not in serialized
    assert "[REDACTED]" in serialized
