import json

from fastapi.testclient import TestClient

from harness.observability import ObservabilityDB, index_runs
from harness.reporting.dashboard import create_dashboard

CANARY = "sk-test-canary-12345"


def _write_desktop_failure_run(tmp_path):
    run = tmp_path / "runs" / "run-1"
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "workflow": "desktop-wf",
                "schema_version": 1,
                "status": "failed",
                "started_at": "2026-06-17T00:00:00Z",
                "finished_at": "2026-06-17T00:00:01Z",
                "report": "report.html",
                "timeline": "timeline.jsonl",
                "records": "records.jsonl",
                "redaction": {"status": "redacted"},
            }
        ),
        encoding="utf-8",
    )
    (run / "timeline.jsonl").write_text("", encoding="utf-8")
    (run / "records.jsonl").write_text("", encoding="utf-8")
    (run / "evidence_bundle.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "run_id": "run-1",
                "workflow_name": "desktop-wf",
                "step_id": "click_submit",
                "failure_kind": "selector_not_found",
                "target_type": "desktop",
                "input_record_id": "row-1",
                "artifacts": {
                    "screenshot": "screenshots/failure.png",
                    "uia_snapshot": "artifacts/uia_tree.json",
                    "win32_snapshot": "artifacts/win32_tree.json",
                    "ocr_artifact": "artifacts/ocr_result.json",
                    "selector_evidence": "artifacts/selector_evidence.json",
                    "repair_packet": "repair_packet.json",
                },
                "desktop": {
                    "backend": "win32",
                    "selector_quality": "weak",
                    "weak_step_reason": "tree path fallback",
                    "verification_method": "ocr_wait",
                    "note": f"token={CANARY}",
                },
                "redaction": {"status": "redacted"},
            }
        ),
        encoding="utf-8",
    )
    (run / "repair_packet.json").write_text(
        json.dumps(
            {
                "workflow_name": "desktop-wf",
                "step_id": "click_submit",
                "failure_kind": "selector_not_found",
                "recommended_next_action": "Run desktop selector discovery.",
            }
        ),
        encoding="utf-8",
    )
    return run


def test_observability_indexes_desktop_evidence_artifacts(tmp_path):
    _write_desktop_failure_run(tmp_path)
    db_path = tmp_path / "runs" / "observability.db"

    result = index_runs(tmp_path / "runs", db_path)
    db = ObservabilityDB(db_path)
    try:
        evidence = db.get_desktop_evidence(run_id="run-1")
    finally:
        db.close()

    assert result["indexed_runs"] == 1
    assert len(evidence) == 1
    item = evidence[0]
    assert item["desktop_backend"] == "win32"
    assert item["selector_quality"] == "weak"
    assert item["weak_step_reason"] == "tree path fallback"
    assert item["verification_method"] == "ocr_wait"
    assert item["uia_snapshot_path"].endswith(
        ("artifacts\\uia_tree.json", "artifacts/uia_tree.json")
    )
    assert item["win32_snapshot_path"].endswith(
        ("artifacts\\win32_tree.json", "artifacts/win32_tree.json")
    )
    assert item["ocr_artifact_path"].endswith(
        ("artifacts\\ocr_result.json", "artifacts/ocr_result.json")
    )
    assert CANARY.encode() not in db_path.read_bytes()


def test_dashboard_exposes_desktop_evidence_read_only(tmp_path):
    _write_desktop_failure_run(tmp_path)
    index_runs(tmp_path / "runs", tmp_path / "runs" / "observability.db")
    client = TestClient(create_dashboard(root_dir=tmp_path))

    response = client.get("/api/desktop/evidence", params={"run_id": "run-1"})
    payload = response.json()
    evidence_id = payload["evidence"][0]["id"]
    detail = client.get(f"/api/desktop/evidence/{evidence_id}")
    missing = client.get("/api/desktop/evidence/999999")

    assert response.status_code == 200
    assert payload["evidence"][0]["desktop_backend"] == "win32"
    assert CANARY not in json.dumps(payload)
    assert detail.status_code == 200
    assert detail.json()["id"] == evidence_id
    assert missing.status_code == 404
