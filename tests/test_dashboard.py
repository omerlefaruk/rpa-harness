import pytest
from fastapi.testclient import TestClient

from harness.reporting.dashboard import create_dashboard, read_jsonl_tail, serve_dashboard


@pytest.mark.asyncio
async def test_serve_dashboard_awaits_uvicorn_server(monkeypatch):
    events = {}

    class FakeConfig:
        def __init__(self, app, host, port, log_level):
            events["app_title"] = app.title
            events["host"] = host
            events["port"] = port
            events["log_level"] = log_level

    class FakeServer:
        def __init__(self, config):
            events["server_config"] = config

        async def serve(self):
            events["served"] = True

    import uvicorn

    monkeypatch.setattr(uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    await serve_dashboard(port=18080, report_dir="./reports")

    assert events == {
        "app_title": "RPA Harness Dashboard",
        "host": "0.0.0.0",
        "port": 18080,
        "log_level": "info",
        "server_config": events["server_config"],
        "served": True,
    }


def test_dashboard_status_reads_supervisor_events(tmp_path):
    session_dir = tmp_path / ".autoresearch"
    session_dir.mkdir()
    (session_dir / "supervisor.jsonl").write_text(
        '{"status":"experiment_rejected","timestamp":"2026-05-01T12:00:00Z"}\n',
        encoding="utf-8",
    )
    app = create_dashboard(root_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/api/autoresearch/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supervisor"]["latest"]["status"] == "experiment_rejected"
    assert "git" in payload


def test_read_jsonl_tail_skips_invalid_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"status":"ok"}\nnot-json\n{"status":"fail"}\n', encoding="utf-8")

    entries = read_jsonl_tail(path, limit=3)

    assert [entry["status"] for entry in entries] == ["ok", "fail"]
