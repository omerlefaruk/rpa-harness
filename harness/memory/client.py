"""
HTTP client for the RPA Memory service.
"""

from __future__ import annotations

from typing import Any

import httpx

from harness.logger import HarnessLogger
from harness.memory.config import MemoryConfig
from harness.memory.errors import MemoryUnavailableError
from harness.security import redact_value


class MemoryClient:
    def __init__(
        self,
        config: MemoryConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: HarnessLogger | None = None,
    ):
        self.config = config or MemoryConfig.from_env()
        self.logger = logger or HarnessLogger("rpa-memory")
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def start_session(
        self,
        content_session_id: str,
        project: str,
        prompt: str = "",
        platform_source: str = "rpa-harness",
        custom_title: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/sessions/init",
            json={
                "contentSessionId": content_session_id,
                "project": project,
                "prompt": prompt,
                "platformSource": platform_source,
                "customTitle": custom_title,
            },
        )

    async def record_observation(
        self,
        content_session_id: str,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        tool_response: Any = None,
        cwd: str = "",
        platform_source: str = "rpa-harness",
        tool_use_id: str | None = None,
        agent_id: str | None = None,
        agent_type: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/sessions/observations",
            json={
                "contentSessionId": content_session_id,
                "tool_name": tool_name,
                "tool_input": tool_input or {},
                "tool_response": tool_response,
                "cwd": cwd,
                "platformSource": platform_source,
                "tool_use_id": tool_use_id,
                "agentId": agent_id,
                "agentType": agent_type,
            },
        )

    async def summarize(
        self,
        content_session_id: str,
        last_assistant_message: str,
        platform_source: str = "rpa-harness",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/sessions/summarize",
            json={
                "contentSessionId": content_session_id,
                "last_assistant_message": last_assistant_message,
                "platformSource": platform_source,
            },
        )

    async def save_memory(
        self,
        text: str,
        title: str | None = None,
        project: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/memory/save",
            json={
                "text": text,
                "title": title,
                "project": project,
                "metadata": metadata or {},
            },
        )

    async def search(
        self,
        query: str | None = None,
        project: str | None = None,
        type: str | None = None,
        obs_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "date_desc",
    ) -> dict[str, Any]:
        params = {
            "query": query,
            "project": project,
            "type": type,
            "obs_type": obs_type,
            "limit": limit,
        }
        if offset:
            params["offset"] = offset
        if order_by != "date_desc":
            params["orderBy"] = order_by
        return await self._request("GET", "/api/search", params=params)

    async def timeline(
        self,
        anchor: int | None = None,
        query: str | None = None,
        project: str | None = None,
        depth_before: int = 3,
        depth_after: int = 3,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/timeline",
            params={
                "anchor": anchor,
                "query": query,
                "project": project,
                "depth_before": depth_before,
                "depth_after": depth_after,
            },
        )

    async def get_observations(
        self,
        ids: list[int],
        project: str | None = None,
        order_by: str = "date_desc",
        limit: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"ids": ids, "project": project}
        if order_by != "date_desc":
            payload["orderBy"] = order_by
        if limit is not None:
            payload["limit"] = limit
        return await self._request("POST", "/api/observations/batch", json=payload)

    async def context_inject(
        self,
        project: str,
        full: bool = False,
    ) -> str:
        result = await self._request(
            "GET",
            "/api/context/inject",
            params={"project": project, "full": str(full).lower()},
            expect_json=False,
        )
        return "" if isinstance(result, dict) and result.get("status") != "ok" else str(result)

    async def semantic_context(
        self,
        query: str,
        project: str | None = None,
        limit: int = 5,
    ) -> str:
        result = await self._request(
            "POST",
            "/api/context/semantic",
            json={"q": query, "project": project, "limit": limit},
        )
        if isinstance(result, dict):
            return str(result.get("context") or "")
        return ""

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> dict[str, Any] | str:
        if not self.config.enabled:
            return {"status": "disabled"}

        safe_json = redact_value(json or {})
        safe_params = {
            key: value for key, value in redact_value(params or {}).items()
            if value is not None
        }

        try:
            async with httpx.AsyncClient(
                base_url=self.config.worker_url.rstrip("/"),
                timeout=self.config.request_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    json=safe_json if json is not None else None,
                    params=safe_params if params else None,
                )
                response.raise_for_status()
                if expect_json:
                    return response.json()
                return response.text
        except Exception as exc:
            message = "memory worker unavailable"
            if self.config.required:
                raise MemoryUnavailableError(message) from exc
            self.logger.warning(message)
            return {"available": False, "error": message, "results": []}
