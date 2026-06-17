from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_design_contract_is_authoritative():
    assert (ROOT / "DESIGN.md").exists()
    assert not (ROOT / "design-elevenlabs.md").exists()


def test_react_dashboard_is_minimal_operator_monitor():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert 'type Tab = "monitor" | "history" | "builder";' in app
    assert app.count('["') == 3
    assert "ProcessRail" in app
    assert "OperatorPanel" in app
    assert "EvidenceTray" in app
    assert "ArtifactPreview" in app
    assert '"gif"' in app
    assert '"log"' in app
    assert "<DeveloperDetails" in app
    assert "<JsonBlock value={summary}" not in app
    assert "getRunSteps" in client
    assert "getRunFailures" in client
    assert "getDesktopEvidence" in client
