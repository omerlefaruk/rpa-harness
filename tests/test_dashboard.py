import pytest
from fastapi.testclient import TestClient

from harness.builder import create_builder_session
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


def test_dashboard_exposes_runs_and_builder_sessions(tmp_path):
    runs = tmp_path / "runs" / "run-1"
    runs.mkdir(parents=True)
    (runs / "run_manifest.json").write_text(
        '{"run_id":"run-1","workflow":"wf","status":"passed","summary":{"passed_steps":1,"total_steps":1}}',
        encoding="utf-8",
    )
    task = tmp_path / "task.md"
    task.write_text("Build a safe fixture workflow", encoding="utf-8")
    create_builder_session(task, session_id="session-1", root_dir=tmp_path)
    app = create_dashboard(root_dir=tmp_path)
    client = TestClient(app)

    index = client.get("/")
    runs_response = client.get("/api/runs")
    builders_response = client.get("/api/builder/sessions")
    detail_response = client.get("/api/builder/sessions/session-1")

    assert index.status_code == 200
    assert "YAML Runs" in index.text
    assert "Builder Sessions" in index.text
    assert runs_response.json()["runs"][0]["run_id"] == "run-1"
    assert builders_response.json()["sessions"][0]["session_id"] == "session-1"
    assert detail_response.json()["session_id"] == "session-1"


def test_read_jsonl_tail_skips_invalid_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"status":"ok"}\nnot-json\n{"status":"fail"}\n', encoding="utf-8")

    entries = read_jsonl_tail(path, limit=3)

    assert [entry["status"] for entry in entries] == ["ok", "fail"]
