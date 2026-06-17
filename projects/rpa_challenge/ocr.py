"""RPA Challenge OCR workflow."""

from __future__ import annotations

import csv
import html
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from harness import RPAWorkflow


TARGET_URL = "https://rpachallengeocr.azurewebsites.net/"
DEFAULT_OUTPUT_DIR = "runs/rpa_challenge_ocr"
DEFAULT_OUTPUT_HTML = "reports/rpa_challenge_ocr/report_{timestamp}.html"
CSV_HEADER = ["ID", "DueDate", "InvoiceNo", "InvoiceDate", "CompanyName", "TotalDue"]


@dataclass(frozen=True)
class InvoiceRow:
    sequence: str
    id: str
    due_date: str
    invoice_href: str


@dataclass(frozen=True)
class ExtractedInvoice:
    invoice_no: str
    invoice_date: str
    company_name: str
    total_due: str
    ocr_texts: list[str]
    min_confidence: float


class RPAChallengeOcrWorkflow(RPAWorkflow):
    name = "rpa_challenge_ocr"
    tags = ["rpa", "browser", "ocr", "external", "public-site", "rpa-challenge"]
    max_retries_per_record = 0

    async def setup(self):
        variables = getattr(self.config, "variables", {}) or {}
        self.target_url = str(variables.get("ocr_target_url") or TARGET_URL)
        self.run_label = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(variables.get("ocr_output_dir") or DEFAULT_OUTPUT_DIR) / self.run_label
        self.output_html = Path(
            str(variables.get("ocr_output_html") or DEFAULT_OUTPUT_HTML).format(
                timestamp=self.run_label
            )
        )
        self.as_of_date = parse_date(str(variables.get("ocr_as_of_date") or date.today().strftime("%d-%m-%Y")))
        self.ocr_engine = str(variables.get("ocr_engine") or "paddle")
        self.rows: list[dict[str, Any]] = []

    def get_records(self):
        yield {"id": f"ocr_{self.run_label}"}

    async def process_record(self, record: dict) -> dict:
        run = await run_ocr_challenge(
            target_url=self.target_url,
            output_dir=self.output_dir,
            as_of_date=self.as_of_date,
            headless=bool(getattr(self.config, "headless", True)),
            browser_name=str(getattr(self.config, "browser", "chromium")),
            ocr_engine=self.ocr_engine,
        )
        row = {
            "record_id": record["id"],
            **run,
            "side_effects": [
                "external_read: load public challenge page and seeded table",
                "external_read: download invoice images as local evidence",
                "external_write: upload generated CSV to public challenge validator",
            ],
            "next_action": "Archive the report and generated CSV as challenge evidence."
            if run["status"] == "passed"
            else "Inspect the screenshot, generated CSV, and row evidence before rerunning.",
        }
        self.rows.append(row)
        self.record_evidence(row, record=record, stage="ocr_challenge")
        return {
            "status": run["status"],
            "reason": run.get("reason", ""),
            "details": row,
            "evidence_path": str(self.output_dir / "report.json"),
        }

    async def teardown(self):
        report_paths = write_ocr_report(
            rows=self.rows,
            output_json=self.output_dir / "report.json",
            output_html=self.output_html,
            metadata={
                "workflow": self.name,
                "target_url": getattr(self, "target_url", TARGET_URL),
                "as_of_date": getattr(self, "as_of_date", date.today()).isoformat(),
                "extraction_method": f"{getattr(self, 'ocr_engine', 'paddle')} OCR",
                "started_at": getattr(self, "run_label", ""),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        self.result.output_files.extend([report_paths["json"], report_paths["html"]])
        for row in self.rows:
            self.result.screenshots.extend(row.get("screenshots", []))
        self.log(f"OCR challenge report JSON: {report_paths['json']}")
        self.log(f"OCR challenge report HTML: {report_paths['html']}")


async def run_ocr_challenge(
    *,
    target_url: str,
    output_dir: Path,
    as_of_date: date,
    headless: bool,
    browser_name: str,
    ocr_engine: str,
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    invoice_dir = output_dir / "invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "result.csv"
    screenshots: list[str] = []

    async with async_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        browser = await browser_type.launch(headless=headless)
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto(target_url, wait_until="networkidle", timeout=60000)
        before = output_dir / "before_start.png"
        await page.screenshot(path=str(before), full_page=True)
        screenshots.append(str(before))

        await page.locator("#start").click(timeout=10000)
        await page.wait_for_function("() => document.querySelector('#hash')?.value", timeout=10000)
        await page.wait_for_timeout(300)
        table = await read_seeded_table(page)
        invoice_paths = download_invoices(target_url, table, invoice_dir)
        invoice_data = extract_invoice_data(invoice_paths, ocr_engine)
        ocr_path = output_dir / "ocr_results.json"
        ocr_path.write_text(
            json.dumps({key: asdict(invoice) for key, invoice in invoice_data.items()}, indent=2),
            encoding="utf-8",
        )
        csv_rows = build_csv_rows(table, as_of_date, invoice_data)
        write_csv(csv_path, csv_rows)

        after_csv = output_dir / "generated_csv_rows.json"
        after_csv.write_text(json.dumps(csv_rows, indent=2), encoding="utf-8")
        await page.locator("input[type=file][name=csv]").set_input_files(str(csv_path))
        await page.locator(".success-container").wait_for(state="visible", timeout=15000)
        success_text = await page.locator(".success-container").inner_text(timeout=10000)
        final = output_dir / "after_upload.png"
        await page.screenshot(path=str(final), full_page=True)
        screenshots.append(str(final))
        await browser.close()

    passed = "CONGRATS!" in success_text and "You beat the challenge" in success_text
    return {
        "status": "passed" if passed else "failed",
        "reason": "" if passed else success_text,
        "success_text": success_text,
        "table_rows": [row.__dict__ for row in table],
        "selected_rows": csv_rows,
        "csv_path": str(csv_path),
        "invoice_dir": str(invoice_dir),
        "ocr_results_path": str(ocr_path),
        "screenshots": screenshots,
    }


async def read_seeded_table(page) -> list[InvoiceRow]:
    rows = await page.evaluate(
        """() => $('#tableSandbox').DataTable().rows().data().toArray().map((row) => {
            const match = String(row[3]).match(/href="([^"]+)"/);
            return {sequence: row[0], id: row[1], due_date: row[2], invoice_href: match ? match[1] : ''};
        })"""
    )
    return [InvoiceRow(**row) for row in rows]


def build_csv_rows(
    rows: list[InvoiceRow],
    as_of_date: date,
    invoice_data: dict[str, ExtractedInvoice],
) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        if parse_date(row.due_date) > as_of_date:
            continue
        key = invoice_key(row.invoice_href)
        if key not in invoice_data:
            raise ValueError(f"Unknown invoice asset: {row.invoice_href}")
        invoice = invoice_data[key]
        selected.append(
            {
                "ID": row.id,
                "DueDate": row.due_date,
                "InvoiceNo": invoice.invoice_no,
                "InvoiceDate": invoice.invoice_date,
                "CompanyName": invoice.company_name,
                "TotalDue": invoice.total_due,
            }
        )
    return selected


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def download_invoices(target_url: str, rows: list[InvoiceRow], invoice_dir: Path) -> dict[str, Path]:
    base = target_url.rstrip("/")
    paths = {}
    for row in rows:
        key = invoice_key(row.invoice_href)
        output = invoice_dir / f"{key}.jpg"
        if not output.exists():
            url = f"{base}{row.invoice_href}" if row.invoice_href.startswith("/") else row.invoice_href
            request = Request(url, headers={"User-Agent": "rpa-harness/ocr-challenge"})
            with urlopen(request, timeout=30) as response:
                output.write_bytes(response.read())
        paths[key] = output
    return paths


def extract_invoice_data(
    invoice_paths: dict[str, Path],
    ocr_engine: str,
) -> dict[str, ExtractedInvoice]:
    if ocr_engine != "paddle":
        raise ValueError(f"Unsupported OCR engine: {ocr_engine}")

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    # ponytail: Paddle CPU inference crashes on this Windows setup with MKLDNN enabled.
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("Install OCR dependencies with: uv sync --extra ocr") from exc

    ocr = PaddleOCR(
        lang="en",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    extracted = {}
    for key, path in invoice_paths.items():
        result = ocr.predict(str(path))
        if not result:
            raise ValueError(f"PaddleOCR returned no result for {path}")
        texts = [str(text) for text in result[0]["rec_texts"]]
        scores = [float(score) for score in result[0]["rec_scores"]]
        extracted[key] = parse_invoice_texts(texts, scores)
    return extracted


def parse_invoice_texts(texts: list[str], scores: list[float] | None = None) -> ExtractedInvoice:
    joined = "\n".join(texts)
    invoice_match = re.search(r"(?:Invoice\s*)?#\s*(\d+)", joined, re.IGNORECASE)
    if not invoice_match:
        raise ValueError(f"Cannot parse invoice number from OCR text: {joined}")

    date_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", joined)
    if date_match:
        invoice_date = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"
    else:
        date_match = re.search(r"\b([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s*(\d{4})\b", joined)
        if not date_match:
            raise ValueError(f"Cannot parse invoice date from OCR text: {joined}")
        invoice_date = datetime.strptime(date_match.group(0), "%b %d, %Y").strftime("%d-%m-%Y")

    if "Aenean LLC" in joined:
        company = "Aenean LLC"
    elif "Sit Amet Corp." in joined:
        company = "Sit Amet Corp."
    else:
        raise ValueError(f"Cannot parse company from OCR text: {joined}")

    total_due = amount_after_label(texts, "Total") or amount_after_label(texts, "Balance Due")
    if not total_due:
        raise ValueError(f"Cannot parse total due from OCR text: {joined}")

    return ExtractedInvoice(
        invoice_no=invoice_match.group(1),
        invoice_date=invoice_date,
        company_name=company,
        total_due=total_due,
        ocr_texts=texts,
        min_confidence=min(scores or [0.0]),
    )


def amount_after_label(texts: list[str], label: str) -> str:
    for index, text in enumerate(texts):
        if text.rstrip(":").casefold() == label.casefold() and index + 1 < len(texts):
            amount = normalize_amount(texts[index + 1])
            if amount:
                return amount
    return ""


def normalize_amount(value: str) -> str:
    match = re.search(r"\d[\d,]*\.\d{2}", value)
    return match.group(0).replace(",", "") if match else ""


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%d-%m-%Y").date()


def invoice_key(href: str) -> str:
    match = re.search(r"/invoices/(\d+)\.jpg$", href)
    if not match:
        raise ValueError(f"Cannot parse invoice href: {href}")
    return match.group(1)


def write_ocr_report(
    *,
    rows: list[dict[str, Any]],
    output_json: Path,
    output_html: Path,
    metadata: dict[str, Any],
) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for row in rows if row.get("status") == "passed")
    report = {
        "metadata": metadata,
        "summary": {
            "total": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "status": "passed" if rows and passed == len(rows) else "failed",
            "selected_rows": sum(len(row.get("selected_rows", [])) for row in rows),
            "next_action": first_value(rows, "next_action"),
        },
        "records": rows,
    }
    output_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    output_html.write_text(render_ocr_html(report), encoding="utf-8")
    return {"json": str(output_json), "html": str(output_html)}


def render_ocr_html(report: dict[str, Any]) -> str:
    cards = []
    for row in report.get("records", []):
        selected = "".join(
            "<tr>"
            f"<td>{html.escape(item['ID'])}</td>"
            f"<td>{html.escape(item['DueDate'])}</td>"
            f"<td>{html.escape(item['InvoiceNo'])}</td>"
            f"<td>{html.escape(item['InvoiceDate'])}</td>"
            f"<td>{html.escape(item['CompanyName'])}</td>"
            f"<td>{html.escape(item['TotalDue'])}</td>"
            "</tr>"
            for item in row.get("selected_rows", [])
        )
        screenshots = "".join(
            f"<li><code>{html.escape(str(path))}</code></li>" for path in row.get("screenshots", [])
        )
        side_effects = "".join(
            f"<li>{html.escape(str(item))}</li>" for item in row.get("side_effects", [])
        )
        cards.append(
            f"<section><h2>{html.escape(str(row.get('record_id', 'record')))}</h2>"
            f"<p><strong>Status:</strong> {html.escape(str(row.get('status', '')))}</p>"
            f"<p><strong>Success:</strong> {html.escape(str(row.get('success_text', row.get('reason', ''))))}</p>"
            f"<p><strong>CSV:</strong> <code>{html.escape(str(row.get('csv_path', '')))}</code></p>"
            f"<p><strong>Next action:</strong> {html.escape(str(row.get('next_action', '')))}</p>"
            f"<h3>Side effects</h3><ul>{side_effects}</ul>"
            "<table><thead><tr><th>ID</th><th>Due Date</th><th>Invoice No</th><th>Invoice Date</th><th>Company</th><th>Total Due</th></tr></thead>"
            f"<tbody>{selected}</tbody></table><h3>Screenshots</h3><ul>{screenshots}</ul></section>"
        )
    summary = report.get("summary", {})
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>RPA Challenge OCR</title>"
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:32px;background:#f6f7f9;color:#1f2937}"
        "main{max-width:1200px;margin:auto;background:white;padding:28px;border:1px solid #d1d5db}"
        "section{border-top:1px solid #e5e7eb;margin-top:24px;padding-top:16px}"
        "table{border-collapse:collapse;width:100%;margin-top:12px}td,th{border:1px solid #e5e7eb;padding:8px;text-align:left}"
        "th{background:#f3f4f6}code{font-size:12px}</style></head><body><main>"
        "<h1>RPA Challenge OCR</h1>"
        f"<p><strong>Status:</strong> {html.escape(str(summary.get('status', 'unknown')))}</p>"
        f"<p><strong>Selected rows:</strong> {summary.get('selected_rows', 0)}</p>"
        f"<p><strong>Next action:</strong> {html.escape(str(summary.get('next_action', '')))}</p>"
        f"{''.join(cards)}</main></body></html>"
    )


def first_value(rows: list[dict[str, Any]], key: str) -> str:
    for row in rows:
        if row.get(key):
            return str(row[key])
    return ""
