"""Contract: legacy YAML/controller entrypoints are gone."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


REMOVED_MODULES = (
    "harness.rpa.yaml_runner",
    "harness.dsl",
    "harness.autopilot",
    "harness.copilot",
    "harness.copilot_session",
    "harness.builder",
    "harness.ai.agent",
    "harness.desktop.ai_controller",
)


@pytest.mark.parametrize("module_name", REMOVED_MODULES)
def test_legacy_modules_are_removed(module_name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_cli_has_no_yaml_flags():
    from harness import cli

    source = Path(cli.__file__).read_text(encoding="utf-8")
    for banned in (
        "--run-yaml",
        "--validate-yaml",
        "yaml_runner",
        "YamlWorkflowRunner",
        "copilot_session",
        "from harness.dsl",
    ):
        assert banned not in source


def test_workflows_and_projects_trees_removed():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "workflows").exists()
    assert not (root / "projects").exists()
