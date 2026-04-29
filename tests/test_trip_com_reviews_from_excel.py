"""Unit tests for the Trip.com Excel review workflow helpers."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "rpa" / "trip_com_reviews_from_excel.py"
SPEC = importlib.util.spec_from_file_location("trip_com_reviews_from_excel", MODULE_PATH)
trip_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = trip_workflow
SPEC.loader.exec_module(trip_workflow)


def test_as_of_date_uses_configured_value():
    assert trip_workflow._as_of_date("2026-04-29") == date(2026, 4, 29)


def test_as_of_date_uses_environment_override(monkeypatch):
    monkeypatch.setenv("TRIP_REVIEW_AS_OF_DATE", "2026-05-10")

    assert trip_workflow._as_of_date() == date(2026, 5, 10)


def test_as_of_date_defaults_to_run_date(monkeypatch):
    monkeypatch.delenv("TRIP_REVIEW_AS_OF_DATE", raising=False)

    assert trip_workflow._as_of_date() == date.today()
