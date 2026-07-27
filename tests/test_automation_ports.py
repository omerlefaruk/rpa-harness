"""Tests for capability port adapters and build_executor port names."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from harness.automation.agent_ops import build_executor
from harness.automation.capabilities import FakeBrowser
from harness.automation.evidence import export_run_evidence, run_evidence_payload
from harness.automation.models import EvidenceReference, RunSummary
from harness.automation.ports import ExcelFilePort, HttpApiPort


def test_build_executor_fake_browser_default():
    executor = build_executor("fake_browser")
    assert isinstance(executor.browser, FakeBrowser)
    assert executor.api is None


def test_build_executor_api_uses_http_port():
    executor = build_executor("api")
    assert isinstance(executor.api, HttpApiPort)
    assert executor.browser is None


def test_build_executor_browser_uses_playwright_port():
    from harness.automation.ports import SyncPlaywrightBrowserPort

    executor = build_executor("browser")
    assert isinstance(executor.browser, SyncPlaywrightBrowserPort)


def test_build_executor_excel_and_desktop_ports():
    from harness.automation.ports import DesktopUiaPort, ExcelFilePort

    excel_ex = build_executor("excel")
    desktop_ex = build_executor("desktop")
    assert isinstance(excel_ex.excel, ExcelFilePort)
    assert isinstance(desktop_ex.desktop, DesktopUiaPort)


def test_build_executor_unknown_port():
    with pytest.raises(ValueError, match="unsupported capability port"):
        build_executor("nope")


def test_http_api_port_get_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"count": 3})

    transport = httpx.MockTransport(handler)
    port = HttpApiPort()
    port._client = httpx.Client(transport=transport)
    try:
        result = port.request("GET", "https://example.test/items")
        assert result["status"] == 200
        assert result["json"] == {"count": 3}
        assert "write_outcome" not in result
        assert "evidence_refs" in result
    finally:
        port.close()


def test_http_api_port_post_sets_write_outcome():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"ok": True})

    port = HttpApiPort()
    port._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = port.request("POST", "https://example.test/items", json={"a": 1})
        assert result["status"] == 201
        assert result["write_outcome"] == "applied"
    finally:
        port.close()


def test_excel_file_port_read_write_roundtrip(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "data.xlsx"
    # seed workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["sku", "qty"])
    ws.append(["A1", 3])
    wb.save(path)
    wb.close()

    port = ExcelFilePort()
    read = port.read_rows(str(path), "Sheet1")
    assert read["rows"]
    assert read["rows"][0]["sku"] == "A1"

    written = port.write_rows(
        str(path),
        "Out",
        [{"sku": "B2", "qty": 9}],
    )
    assert written["written"] == 1
    assert written["write_outcome"] == "applied"

    again = port.read_rows(str(path), "Out")
    assert again["rows"][0]["sku"] == "B2"
    assert again["rows"][0]["qty"] == 9


def test_export_run_evidence_writes_redacted_json(tmp_path: Path):
    summary = RunSummary(
        run_id="run_test",
        definition_id="def1",
        status="completed",
        verification_results=({"passed": True, "message": "ok"},),
        evidence_references=(
            EvidenceReference(evidence_id="e1", uri="evidence/run_test.json", kind="verification"),
        ),
    )
    path = export_run_evidence(summary, tmp_path)
    assert path.exists()
    payload = run_evidence_payload(summary)
    assert payload["run_id"] == "run_test"
    assert payload["status"] == "completed"
    text = path.read_text(encoding="utf-8")
    assert "run_test" in text
    assert "evidence_references" in text


@pytest.mark.skipif(
    __import__("sys").platform.startswith("win") is False,
    reason="DesktopUiaPort requires Windows",
)
def test_desktop_uia_port_missing_pywinauto_message(monkeypatch):
    import builtins

    from harness.automation.ports import DesktopUiaPort

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pywinauto" or name.startswith("pywinauto."):
            raise ImportError("no pywinauto")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    port = DesktopUiaPort()
    with pytest.raises(RuntimeError, match="desktop driver not available"):
        port.launch("notepad.exe")
