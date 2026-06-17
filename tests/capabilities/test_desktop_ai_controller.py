import json
import subprocess
import sys

from harness.desktop.ai_controller import DesktopAIController


def _evidence_session(tmp_path):
    session = tmp_path / "desktop-session"
    artifacts = session / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "uia_tree.json").write_text(
        json.dumps({"name": "Legacy ERP", "children": [{"automation_id": "Submit"}]}),
        encoding="utf-8",
    )
    (session / "evidence_bundle.json").write_text(
        json.dumps(
            {
                "target_type": "desktop",
                "artifacts": {"uia_snapshot": "artifacts/uia_tree.json"},
                "desktop": {"backend": "uia"},
            }
        ),
        encoding="utf-8",
    )
    return session


def _strong_proposal():
    return {
        "approved": True,
        "side_effect": "none",
        "step": {
            "id": "click_submit",
            "action": {
                "type": "desktop.click",
                "selector": {"strategy": "automation_id", "value": "Submit"},
            },
            "success_check": [{"type": "element_exists"}],
        },
    }


def test_desktop_ai_controller_requires_evidence_before_approved_execution(tmp_path):
    controller = DesktopAIController(tmp_path / "missing-session")

    decision = controller.validate_proposal(
        _strong_proposal(),
        require_approval=True,
        require_evidence=True,
    )

    assert decision["status"] == "blocked"
    assert "desktop discovery evidence is required" in " ".join(decision["issues"])


def test_desktop_ai_controller_rejects_step_without_success_check(tmp_path):
    controller = DesktopAIController(_evidence_session(tmp_path))
    proposal = _strong_proposal()
    proposal["step"].pop("success_check")

    decision = controller.validate_proposal(
        proposal,
        require_approval=True,
        require_evidence=True,
    )

    assert decision["status"] == "blocked"
    assert "success_check" in " ".join(decision["issues"])


def test_desktop_ai_controller_requires_metadata_for_coordinate_fallback(tmp_path):
    controller = DesktopAIController(_evidence_session(tmp_path))
    proposal = {
        "approved": True,
        "side_effect": "none",
        "step": {
            "id": "click_by_ratio",
            "action": {
                "type": "desktop.click",
                "allow_coordinate_fallback": True,
                "selector": {
                    "strategy": "coordinate",
                    "value": {"x_ratio": 0.5, "y_ratio": 0.5},
                },
            },
            "success_check": [{"type": "element_exists"}],
        },
    }

    decision = controller.validate_proposal(
        proposal,
        require_approval=True,
        require_evidence=True,
    )

    assert decision["status"] == "blocked"
    joined = " ".join(decision["issues"])
    assert "weak_step_reason" in joined
    assert "verification_method" in joined


def test_desktop_ai_controller_accepts_approved_deterministic_step(tmp_path):
    session = _evidence_session(tmp_path)
    controller = DesktopAIController(session)
    proposal = _strong_proposal()
    proposal_path = session / "approved_desktop_proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    decision = controller.run("execute-approved", proposal_path=proposal_path)

    assert decision["status"] == "approved"
    assert decision["execution_packet"]["mode"] == "deterministic_yaml_step"
    assert (session / "desktop_ai_execution_decision.json").exists()


def test_desktop_ai_controller_cli_inspect_mode(tmp_path):
    session = _evidence_session(tmp_path)

    completed = subprocess.run(
        [sys.executable, "main.py", "--desktop-ai-assist", str(session), "--mode", "inspect"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "ready"
    assert payload["evidence"]["evidence_files"]
    assert (session / "desktop_ai_inspection.json").exists()
