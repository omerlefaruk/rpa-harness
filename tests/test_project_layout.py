from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from harness.rpa.templates import write_workflow_template


PROJECTS = (
    "example_data_verification",
    "operaRezervasyon",
    "ota_link_swarm",
    "ota_recent_reviews",
    "rpa_challenge",
    "trip_com_reviews",
)


def test_real_projects_use_single_project_folder_layout():
    repo = Path(__file__).resolve().parents[1]
    required_files = (
        "workflows/main.yaml",
        "config.yaml",
        "tests/test_workflow.py",
        "README.md",
    )

    missing = [
        f"projects/{project}/{relative}"
        for project in PROJECTS
        for relative in required_files
        if not (repo / "projects" / project / relative).exists()
    ]

    assert missing == []


def test_real_project_assets_do_not_live_in_legacy_roots():
    repo = Path(__file__).resolve().parents[1]
    legacy_paths = [
        "workflows/operaRezervasyon",
        "workflows/rpa_challenge",
        "config/operaRezervasyon.yaml",
        "config/rpaChallengeOcr.yaml",
        "config/rpaChallengeShortestPath.yaml",
        "tests/rpa/opera_rezervasyon_from_excel.py",
        "tests/rpa/rpa_challenge_ocr.py",
        "tests/rpa/rpa_challenge_shortest_path.py",
        "tests/rpa",
        "tests/test_opera_rezervasyon_workflow.py",
        "tests/test_ota_link_swarm_from_excel.py",
        "tests/test_ota_recent_reviews_from_excel.py",
        "tests/test_trip_com_reviews_from_excel.py",
        "tests/test_rpa_challenge_ocr_workflow.py",
        "tests/test_rpa_challenge_shortest_path_workflow.py",
    ]

    leftovers = [path for path in legacy_paths if (repo / path).exists()]

    assert leftovers == []


def test_new_project_workflows_must_be_written_under_projects():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with pytest.raises(ValueError, match=r"projects/<project>/workflows"):
            write_workflow_template(
                root / "workflows" / "new_api.yaml",
                template="api_read_write",
                workflow_id="new_api",
            )

        path = write_workflow_template(
            root / "projects" / "new_api" / "workflows" / "main.yaml",
            template="api_read_write",
            workflow_id="new_api",
        )

        assert path.exists()
