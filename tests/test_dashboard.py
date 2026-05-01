import pytest

from harness.reporting.dashboard import serve_dashboard


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
