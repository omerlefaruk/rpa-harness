"""
High-level RPA Memory recording helpers.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from harness.logger import HarnessLogger
from harness.memory.client import MemoryClient
from harness.memory.config import MemoryConfig
from harness.memory.errors import MemoryUnavailableError
from harness.security import redact_value


class MemoryRecorder:
    def __init__(
        self,
        config: MemoryConfig | None = None,
        client: MemoryClient | None = None,
        logger: HarnessLogger | None = None,
    ):
        self.config = config or MemoryConfig.from_env()
        self.client = client or MemoryClient(self.config)
        self.logger = logger or HarnessLogger("rpa-memory-recorder")
        self.available = self.config.enabled

    @classmethod
    def from_harness_config(cls, harness_config: Any) -> "MemoryRecorder":
        return cls(config=getattr(harness_config, "memory", None))

    def new_session_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    async def ensure_available(self) -> bool:
        if not self.config.enabled:
            self.available = False
            return False
        result = await self.client.health()
        self.available = not (
            isinstance(result, dict)
            and (result.get("status") == "unavailable" or result.get("available") is False)
        )
        if not self.available and self.config.required:
            raise MemoryUnavailableError(str(result))
        return self.available

    async def start_session(
        self,
        content_session_id: str,
        prompt: str,
        project: str | None = None,
        custom_title: str | None = None,
    ) -> dict[str, Any]:
        return await self.client.start_session(
            content_session_id=content_session_id,
            project=project or self.config.project,
            prompt=prompt,
            platform_source="rpa-harness",
            custom_title=custom_title,
        )

    async def record_observation(
        self,
        content_session_id: str,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        tool_response: Any = None,
        cwd: str | None = None,
        tool_use_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.client.record_observation(
            content_session_id=content_session_id,
            tool_name=tool_name,
            tool_input=redact_value(tool_input or {}),
            tool_response=redact_value(tool_response),
            cwd=cwd or os.getcwd(),
            platform_source="rpa-harness",
            tool_use_id=tool_use_id,
        )

    async def summarize(self, content_session_id: str, summary: Any) -> dict[str, Any]:
        return await self.client.summarize(
            content_session_id=content_session_id,
            last_assistant_message=str(redact_value(summary)),
            platform_source="rpa-harness",
        )

    async def record_test_result(self, content_session_id: str, result: Any) -> None:
        await self.record_observation(
            content_session_id=content_session_id,
            tool_name="test_result",
            tool_input={"name": result.name},
            tool_response=result.to_dict(),
            tool_use_id=f"test-{result.name}",
        )

    async def record_workflow_result(self, content_session_id: str, result: Any) -> None:
        await self.record_observation(
            content_session_id=content_session_id,
            tool_name="workflow_result",
            tool_input={"name": result.name},
            tool_response=result.to_dict(),
            tool_use_id=f"workflow-{result.name}",
        )

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        return await self.client.search(**kwargs)

    async def timeline(self, **kwargs: Any) -> dict[str, Any]:
        return await self.client.timeline(**kwargs)

    async def get_observations(self, **kwargs: Any) -> dict[str, Any]:
        return await self.client.get_observations(**kwargs)

    async def semantic_context(self, query: str, project: str | None = None) -> str:
        if not self.config.semantic_inject:
            return ""
        return await self.client.semantic_context(
            query=query,
            project=project or self.config.project,
            limit=self.config.semantic_inject_limit,
        )
