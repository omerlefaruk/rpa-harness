from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from harness.config import HarnessConfig
from projects.rpa_challenge.ocr import (
    CSV_HEADER,
    ExtractedInvoice,
    InvoiceRow,
    RPAChallengeOcrWorkflow,
    build_csv_rows,
    invoice_key,
    parse_invoice_texts,
    write_csv,
    write_ocr_report,
)
from projects.rpa_challenge.shortest_path import (
    FIXTURE_DEMANDS,
    RPAChallengeShortestPathWorkflow,
    build_round_plan,
    closest_supply,
    fixture_preflight,
    side_effect_summary,
    write_recon_artifact,
    write_shortest_path_report,
)


def test_shortest_path_fixture_has_five_deterministic_pairs():
    plan = build_round_plan(FIXTURE_DEMANDS)

    assert len(plan) == 5
    assert [item["supply"]["_id"] for item in plan] == [
        "G-1001",
        "G-1004",
        "G-1006",
        "G-1001",
        "G-1004",
    ]


def test_closest_supply_uses_geographic_distance():
    supply = closest_supply({"_id": "D-test", "lat": "37.78", "lng": "-122.42"})

    assert supply["_id"] == "G-1004"


def test_rpa_challenge_project_config_covers_both_workflows():
    config = HarnessConfig.from_yaml("projects/rpa_challenge/config.yaml")
    shortest_path = RPAChallengeShortestPathWorkflow(config=config)
    ocr = RPAChallengeOcrWorkflow(config=config)

    assert config.variables["shortest_path_mode"] == "live"
    assert config.variables["shortest_path_recon_dir"].endswith("/recon")
    assert config.variables["ocr_target_url"] == "https://rpachallengeocr.azurewebsites.net/"
    assert config.variables["ocr_engine"] == "paddle"
    assert shortest_path.name == "rpa_challenge_shortest_path"
    assert ocr.name == "rpa_challenge_ocr"


def test_fixture_preflight_is_explicitly_not_live_success():
    preflight = fixture_preflight("https://example.test/page", "http://example.test/api")

    assert preflight["status"] == "passed"
    assert preflight["decision"] == "run_fixture"
    assert preflight["checks"][1]["status"] == "skipped"
    assert "live mode" in preflight["next_action"]
    assert "no challenge backend write" in side_effect_summary("fixture")[-1]


def test_recon_artifact_writer_preserves_preflight_json(tmp_path: Path):
    path = write_recon_artifact(
        {"status": "failed", "reason": "backend down"},
        tmp_path,
        mode="live",
        timestamp="20260617_010203",
    )

    report = json.loads(Path(path).read_text(encoding="utf-8"))
    assert Path(path).name == "preflight_live_20260617_010203.json"
    assert report["reason"] == "backend down"


def test_shortest_path_report_writer(tmp_path: Path):
    output_json = tmp_path / "run.json"
    output_html = tmp_path / "run.html"

    write_shortest_path_report(
        rows=[
            {
                "record_id": "fixture",
                "status": "passed",
                "rounds": [{"round": 1, "demand_id": "D-1", "supply_id": "G-1001"}],
                "success_text": "Your success rate is 100.00%",
                "success_details": "Detailed score: 80 out of 80 input fields.",
                "preflight": fixture_preflight("https://example.test/page", "http://example.test/api"),
                "side_effects": side_effect_summary("fixture"),
                "next_action": "Use live mode when the challenge backend is reachable.",
            }
        ],
        output_json=output_json,
        output_html=output_html,
        metadata={"workflow": "test", "mode": "fixture"},
    )

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["summary"]["status"] == "passed"
    assert report["summary"]["mode"] == "fixture"
    assert report["summary"]["dependency_status"] == "passed"
    html = output_html.read_text(encoding="utf-8")
    assert "D-1" in html
    assert "Next action" in html


def test_invoice_key_parses_challenge_href():
    assert invoice_key("/invoices/10.jpg") == "10"


def test_build_csv_rows_filters_due_dates_and_preserves_order():
    rows = [
        InvoiceRow("1", "past", "16-06-2026", "/invoices/10.jpg"),
        InvoiceRow("2", "today", "17-06-2026", "/invoices/8.jpg"),
        InvoiceRow("3", "future", "18-06-2026", "/invoices/1.jpg"),
    ]

    csv_rows = build_csv_rows(
        rows,
        date(2026, 6, 17),
        {
            "8": ExtractedInvoice("284232", "15-06-2019", "Aenean LLC", "1009.80", [], 1.0),
            "10": ExtractedInvoice("284213", "03-06-2019", "Aenean LLC", "9778.40", [], 1.0),
        },
    )

    assert [row["ID"] for row in csv_rows] == ["past", "today"]
    assert csv_rows[0]["InvoiceNo"] == "284213"
    assert csv_rows[1]["TotalDue"] == "1009.80"


def test_parse_sit_amet_invoice_text():
    invoice = parse_invoice_texts(
        [
            "INVOICE",
            "#11577",
            "Sit Amet Corp.",
            "Date:",
            "Jun 30, 2019",
            "Balance Due:",
            "$17,310.00",
            "Total:",
            "$17,310.00",
        ],
        [0.99],
    )

    assert invoice.invoice_no == "11577"
    assert invoice.invoice_date == "30-06-2019"
    assert invoice.company_name == "Sit Amet Corp."
    assert invoice.total_due == "17310.00"


def test_parse_aenean_invoice_text():
    invoice = parse_invoice_texts(
        [
            "Aenean LLC",
            "INVOICE",
            "2019-06-20",
            "Invoice #284221",
            "Total",
            "6300.00",
        ],
        [0.99],
    )

    assert invoice.invoice_no == "284221"
    assert invoice.invoice_date == "20-06-2019"
    assert invoice.company_name == "Aenean LLC"
    assert invoice.total_due == "6300.00"


def test_write_csv_matches_expected_header(tmp_path: Path):
    csv_path = tmp_path / "result.csv"
    write_csv(
        csv_path,
        [
            {
                "ID": "abc",
                "DueDate": "17-06-2026",
                "InvoiceNo": "11577",
                "InvoiceDate": "30-06-2019",
                "CompanyName": "Sit Amet Corp.",
                "TotalDue": "17310.00",
            }
        ],
    )

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == CSV_HEADER
    assert lines[1] == "abc,17-06-2026,11577,30-06-2019,Sit Amet Corp.,17310.00"


def test_ocr_report_writer_includes_selected_rows(tmp_path: Path):
    output_json = tmp_path / "report.json"
    output_html = tmp_path / "report.html"

    write_ocr_report(
        rows=[
            {
                "record_id": "ocr",
                "status": "passed",
                "success_text": "CONGRATS!\nYou beat the challenge in 1 seconds.",
                "selected_rows": [
                    {
                        "ID": "abc",
                        "DueDate": "17-06-2026",
                        "InvoiceNo": "11577",
                        "InvoiceDate": "30-06-2019",
                        "CompanyName": "Sit Amet Corp.",
                        "TotalDue": "17310.00",
                    }
                ],
                "csv_path": "result.csv",
                "side_effects": ["external_write: upload generated CSV"],
                "next_action": "Archive the report.",
            }
        ],
        output_json=output_json,
        output_html=output_html,
        metadata={"workflow": "test"},
    )

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["summary"]["status"] == "passed"
    assert report["summary"]["selected_rows"] == 1
    assert "Sit Amet Corp." in output_html.read_text(encoding="utf-8")
