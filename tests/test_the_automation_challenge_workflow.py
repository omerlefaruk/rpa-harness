from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from harness.config import HarnessConfig
from projects.rpa_challenge import the_automation_challenge as challenge_module
from projects.rpa_challenge.the_automation_challenge import (
    HEADERS,
    TheAutomationChallengeWorkflow,
    read_rows,
    write_report,
)


def test_config_loads_workflow():
    config = HarnessConfig.from_yaml("config/theAutomationChallenge.yaml")
    workflow = TheAutomationChallengeWorkflow(config=config)

    assert workflow.name == "the_automation_challenge"
    assert config.variables["automation_challenge_url"] == "https://www.theautomationchallenge.com/"


def test_read_rows_validates_headers(tmp_path: Path):
    path = tmp_path / "challenge.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    sheet.append(
        [
            "80-1579069",
            "Meetz",
            "Technology",
            "9 Thompson Center",
            "UiPath",
            "$282317.42",
            "25/07/2019",
        ]
    )
    workbook.save(path)

    assert read_rows(path) == [
        {
            "employer_identification_number": "80-1579069",
            "company_name": "Meetz",
            "sector": "Technology",
            "company_address": "9 Thompson Center",
            "automation_tool": "UiPath",
            "annual_automation_saving": "$282317.42",
            "date_of_first_project": "25/07/2019",
        }
    ]


def test_report_writer_records_success(tmp_path: Path):
    output_json = tmp_path / "report.json"
    output_html = tmp_path / "report.html"

    write_report(
        rows=[
            {
                "record_id": "record",
                "status": "passed",
                "result_text": "SUCCESS!\nYour success rate is 100%",
                "row_count": 50,
                "captcha_cleared": 1,
                "screenshots": ["final.png"],
                "next_action": "Archive.",
            }
        ],
        output_json=output_json,
        output_html=output_html,
        metadata={"workflow": "test"},
    )

    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["summary"]["status"] == "passed"
    assert "SUCCESS!" in output_html.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_workflow_writes_challenge_progress_events(tmp_path: Path, monkeypatch):
    async def fake_run_challenge(**kwargs):
        kwargs["progress"](
            "challenge.row.submitted",
            status="running",
            message="Row 1/1 submitted",
        )
        return {
            "status": "passed",
            "reason": "",
            "result_text": "SUCCESS!",
            "workbook_path": str(tmp_path / "challenge.xlsx"),
            "row_count": 1,
            "captcha_cleared": 0,
            "screenshots": [],
        }

    monkeypatch.setattr(challenge_module, "run_challenge", fake_run_challenge)
    config = HarnessConfig(
        headless=True,
        enable_vision=False,
        enable_agent=False,
        report_dir=str(tmp_path / "reports"),
        variables={
            "runs_dir": str(tmp_path / "runs"),
            "automation_challenge_output_dir": str(tmp_path / "challenge"),
            "automation_challenge_output_html": str(tmp_path / "report_{timestamp}.html"),
        },
    )

    result = await TheAutomationChallengeWorkflow(config=config)._execute()
    timeline = (Path(result.data["run_dir"]) / "timeline.jsonl").read_text(encoding="utf-8")

    assert result.status.value == "passed"
    assert "challenge.row.submitted" in timeline
    assert "Row 1/1 submitted" in timeline
