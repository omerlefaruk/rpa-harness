"""
RPA Memory HTTP service.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from harness.memory.config import MemoryConfig
from harness.memory.store import MemoryStore


class SessionInitRequest(BaseModel):
    content_session_id: Optional[str] = Field(default=None, alias="contentSessionId")
    project: str = "rpa-harness"
    prompt: str = ""
    platform_source: str = Field(default="rpa-harness", alias="platformSource")
    custom_title: Optional[str] = Field(default=None, alias="customTitle")


class ObservationRequest(BaseModel):
    content_session_id: Optional[str] = Field(default=None, alias="contentSessionId")
    tool_name: str
    tool_input: Dict[str, Any] = Field(default_factory=dict)
    tool_response: Any = None
    cwd: str = ""
    agent_id: Optional[str] = Field(default=None, alias="agentId")
    agent_type: Optional[str] = Field(default=None, alias="agentType")


class SummarizeRequest(BaseModel):
    content_session_id: Optional[str] = Field(default=None, alias="contentSessionId")
    last_assistant_message: str = ""


class ManualMemoryRequest(BaseModel):
    text: str
    title: Optional[str] = None
    project: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObservationBatchRequest(BaseModel):
    ids: List[int]
    project: Optional[str] = None
    order_by: str = Field(default="date_desc", alias="orderBy")
    limit: Optional[int] = None


def create_memory_app(db_path: str = "./data/rpa_memory.db") -> FastAPI:
    app = FastAPI(title="RPA Memory", version="0.2.0")
    store = MemoryStore(db_path)

    @app.get("/health")
    async def health():
        return {"status": "ok", "database": str(store.db_path)}

    @app.post("/api/sessions/init")
    async def init_session(request: SessionInitRequest):
        return store.create_or_update_session(
            content_session_id=request.content_session_id or "",
            project=request.project,
            prompt=request.prompt,
            platform_source=request.platform_source,
            custom_title=request.custom_title,
        )

    @app.post("/api/sessions/observations")
    async def add_observation(request: ObservationRequest):
        return store.add_observation(
            content_session_id=request.content_session_id or "",
            tool_name=request.tool_name,
            tool_input=request.tool_input,
            tool_response=request.tool_response,
            cwd=request.cwd,
            agent_id=request.agent_id,
            agent_type=request.agent_type,
        )

    @app.post("/api/sessions/summarize")
    async def summarize(request: SummarizeRequest):
        return store.add_summary(
            content_session_id=request.content_session_id or "",
            last_assistant_message=request.last_assistant_message,
        )

    @app.post("/api/memory/save")
    async def save_memory(request: ManualMemoryRequest):
        return store.save_manual_memory(
            text=request.text,
            title=request.title,
            project=request.project or "rpa-harness",
            metadata=request.metadata,
        )

    @app.get("/api/search")
    async def search(
        query: Optional[str] = None,
        q: Optional[str] = None,
        project: Optional[str] = None,
        type: Optional[str] = None,
        obs_type: Optional[str] = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        orderBy: str = "date_desc",
    ):
        return store.search(
            query=query if query is not None else q,
            project=project,
            result_type=type,
            obs_type=obs_type,
            limit=limit,
            offset=offset,
            order_by=orderBy,
        )

    @app.get("/api/timeline")
    async def timeline(
        anchor: Optional[int] = None,
        query: Optional[str] = None,
        project: Optional[str] = None,
        depth_before: int = Query(3, ge=0, le=20),
        depth_after: int = Query(3, ge=0, le=20),
    ):
        return store.timeline(
            anchor=anchor,
            query=query,
            project=project,
            depth_before=depth_before,
            depth_after=depth_after,
        )

    @app.post("/api/observations/batch")
    async def observations_batch(request: ObservationBatchRequest):
        return store.get_observations(
            ids=request.ids,
            project=request.project,
            order_by=request.order_by,
            limit=request.limit,
        )

    @app.get("/api/context/inject", response_class=PlainTextResponse)
    async def inject_context(project: str, full: bool = False):
        return store.context_for_project(project, limit=50 if full else 10)

    @app.post("/api/context/semantic")
    async def semantic_context(payload: Dict[str, Any]):
        project = payload.get("project") or "rpa-harness"
        limit = int(payload.get("limit") or 5)
        return {
            "context": store.context_for_project(project, limit=limit),
            "count": limit,
        }

    @app.get("/")
    @app.get("/ui")
    async def dashboard():
        return HTMLResponse(_dashboard_html())

    return app


def _dashboard_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>RPA Memory</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; }
    code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>RPA Memory</h1>
  <p>Use <code>/api/search</code>, <code>/api/timeline</code>, and
  <code>/api/observations/batch</code> for progressive retrieval.</p>
</body>
</html>"""


def run_memory_server(
    db_path: str = "./data/rpa_memory.db",
    port: int = 37777,
    host: str = "127.0.0.1",
):
    import uvicorn

    app = create_memory_app(db_path)
    uvicorn.run(app, host=host, port=port, log_level="info")


async def serve_memory_server(
    db_path: str = "./data/rpa_memory.db",
    port: int = 37777,
    host: str = "127.0.0.1",
):
    import uvicorn

    app = create_memory_app(db_path)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    config = MemoryConfig.from_env()
    run_memory_server(db_path=config.db_path, port=int(config.worker_url.rsplit(":", 1)[-1]))
