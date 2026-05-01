import json
from pathlib import Path

from tools import tech_radar


def test_tech_radar_records_changed_source_once(tmp_path, monkeypatch):
    config = tmp_path / "sources.json"
    state = tmp_path / "state.json"
    jsonl = tmp_path / "events.jsonl"
    candidates = tmp_path / "candidates.md"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "name": "Example Source",
                        "url": "https://example.com/docs?token=secret",
                        "category": "browser-automation",
                        "kind": "html",
                        "tags": ["selectors"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_fetch(source, timeout):
        assert source.url == "https://example.com/docs"
        assert timeout == 0.5
        return b"<html><title>New automation release</title></html>", {
            "content-type": "text/html; charset=utf-8"
        }

    monkeypatch.setattr(tech_radar, "fetch_source", fake_fetch)

    first = tech_radar.run_radar(
        config_path=config,
        state_path=state,
        jsonl_path=jsonl,
        candidates_path=candidates,
        timeout=0.5,
        now=1.0,
    )
    second = tech_radar.run_radar(
        config_path=config,
        state_path=state,
        jsonl_path=jsonl,
        candidates_path=candidates,
        timeout=0.5,
        now=2.0,
    )

    assert first["status"] == "ok"
    assert first["changed"] == 1
    assert second["changed"] == 0
    assert jsonl.exists()
    assert len(jsonl.read_text(encoding="utf-8").splitlines()) == 1
    assert "New automation release" in candidates.read_text(encoding="utf-8")
    saved_state = json.loads(state.read_text(encoding="utf-8"))
    assert "https://example.com/docs" in saved_state["sources"]


def test_tech_radar_reports_unavailable_without_failing_by_default(tmp_path, monkeypatch):
    config = tmp_path / "sources.json"
    state = tmp_path / "state.json"
    jsonl = tmp_path / "events.jsonl"
    config.write_text(
        json.dumps({"sources": [{"name": "Down", "url": "https://down.example/"}]}),
        encoding="utf-8",
    )

    def fake_fetch(source, timeout):
        raise OSError("network unavailable")

    monkeypatch.setattr(tech_radar, "fetch_source", fake_fetch)
    summary = tech_radar.run_radar(
        config_path=config,
        state_path=state,
        jsonl_path=jsonl,
        timeout=0.1,
        now=3.0,
    )

    assert summary["status"] == "ok"
    assert summary["changed"] == 0
    assert summary["unavailable"] == 1
    assert state.exists()
    assert not jsonl.exists()


def test_tech_radar_cycle_size_advances_cursor(tmp_path, monkeypatch):
    config = tmp_path / "sources.json"
    state = tmp_path / "state.json"
    jsonl = tmp_path / "events.jsonl"
    candidates = tmp_path / "candidates.md"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {"name": "One", "url": "https://one.example/"},
                    {"name": "Two", "url": "https://two.example/"},
                ]
            }
        ),
        encoding="utf-8",
    )
    seen = []

    def fake_fetch(source, timeout):
        seen.append(source.name)
        return f"<title>{source.name}</title>".encode(), {"content-type": "text/html"}

    monkeypatch.setattr(tech_radar, "fetch_source", fake_fetch)

    first = tech_radar.run_radar(
        config_path=config,
        state_path=state,
        jsonl_path=jsonl,
        candidates_path=candidates,
        cycle_size=1,
        now=4.0,
    )
    second = tech_radar.run_radar(
        config_path=config,
        state_path=state,
        jsonl_path=jsonl,
        candidates_path=candidates,
        cycle_size=1,
        now=5.0,
    )

    assert first["scanned"] == 1
    assert second["scanned"] == 1
    assert seen == ["One", "Two"]
    saved_state = json.loads(state.read_text(encoding="utf-8"))
    assert saved_state["source_cursor"] == 0
