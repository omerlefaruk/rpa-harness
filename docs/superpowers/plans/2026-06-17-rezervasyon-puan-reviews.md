# Rezervasyon Puan Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a project that reads every hotel/platform link from `Branches.xlsx`, visits each hotel review source, extracts reviews from the last 30 days, and writes them to Excel.

**Architecture:** Add one thin project under `projects/rezervasyon_puan_reviews` and reuse the existing OTA review extraction code in `projects/ota_recent_reviews`. Keep the new code limited to project defaults, richer source-Excel metadata, and a workbook shaped for this automation.

**Tech Stack:** Python, `openpyxl`, Playwright through existing `RPAWorkflow`, current `main.py --run-workflows` project discovery.

---

## File Structure

- Create: `projects/rezervasyon_puan_reviews/config.yaml`
  - Project config pointing at `C:/Users/Rau/Desktop/Archive/TM-57-Rezervasyon_Puan/data/Branches.xlsx`.
- Create: `projects/rezervasyon_puan_reviews/workflows/main.yaml`
  - Harness descriptor with explicit success checks and safe side effects.
- Create: `projects/rezervasyon_puan_reviews/README.md`
  - One command to run the automation.
- Create: `projects/rezervasyon_puan_reviews/workflow.py`
  - Thin subclass around `OtaRecentReviewsFromExcelWorkflow`, plus a reader that preserves hotel/platform score and review count from the source workbook.
- Create: `projects/rezervasyon_puan_reviews/tests/test_workflow.py`
  - Focused tests for reading the source workbook shape and writing the Excel report shape.
- Modify: `tests/test_project_layout.py`
  - Add `rezervasyon_puan_reviews` to the real project layout list.

No AI categorization, WhatsApp, CRM, or Google Sheets in this slice. The requested job is last-30-day review extraction into Excel.

---

### Task 1: Project Shell

**Files:**
- Create: `projects/rezervasyon_puan_reviews/config.yaml`
- Create: `projects/rezervasyon_puan_reviews/workflows/main.yaml`
- Create: `projects/rezervasyon_puan_reviews/README.md`

- [ ] **Step 1: Create project directories**

Run:

```powershell
New-Item -ItemType Directory -Force `
  projects/rezervasyon_puan_reviews, `
  projects/rezervasyon_puan_reviews/workflows, `
  projects/rezervasyon_puan_reviews/tests
```

Expected: directories exist.

- [ ] **Step 2: Add config**

Write `projects/rezervasyon_puan_reviews/config.yaml`:

```yaml
name: rezervasyon_puan_reviews
log_level: INFO
report_dir: ./reports
screenshot_dir: ./screenshots
headless: true
browser: chromium

variables:
  input_excel: C:/Users/Rau/Desktop/Archive/TM-57-Rezervasyon_Puan/data/Branches.xlsx
  sheet: Taksim Analiz
  output_json: runs/rezervasyon_puan_reviews/reviews_last_30_days.json
  output_html: reports/rezervasyon_puan_reviews/reviews_last_30_days.html
  output_excel: reports/rezervasyon_puan_reviews/reviews_last_30_days.xlsx
  timeout_ms: 20000
```

- [ ] **Step 3: Add workflow descriptor**

Write `projects/rezervasyon_puan_reviews/workflows/main.yaml`:

```yaml
id: rezervasyon_puan_reviews
name: Rezervasyon Puan Reviews
version: "0.1.0"
type: mixed
description: Reads hotel/platform links from the TM-57 source workbook and writes last-30-day reviews to Excel.
owner: ops
target_systems:
  - ota-public-sites
input_schema:
  input_excel: string
  sheet: string
output_destination: reports/rezervasyon_puan_reviews/reviews_last_30_days.xlsx
system_of_record: public OTA review pages
success_condition: The workflow writes JSON, HTML, and Excel artifacts with one row per parsed recent review.
safe_test_case: Run project unit tests against a generated fixture workbook.
allowed_side_effects:
  - write_report
rerun_policy: Safe to rerun; output files are overwritten.
escalation_owner: ops
inputs:
  input_excel: C:/Users/Rau/Desktop/Archive/TM-57-Rezervasyon_Puan/data/Branches.xlsx
  sheet: Taksim Analiz
steps:
  - id: python_workflow_entrypoint
    current_stage: execute_python_workflow
    intent: Run the project Python RPAWorkflow.
    preconditions:
      - source workbook exists
      - source sheet exists
    postconditions:
      - Excel report exists
      - JSON report exists
      - HTML report exists
    proof: projects/rezervasyon_puan_reviews/tests/test_workflow.py
    failure_path: Fix project tests before production execution.
    action:
      type: no_op
    success_check:
      - type: always_pass
```

- [ ] **Step 4: Add README**

Write `projects/rezervasyon_puan_reviews/README.md`:

````markdown
# rezervasyon_puan_reviews

Reads hotel/platform links from `Branches.xlsx`, visits each OTA review source, extracts reviews from the last 30 days, and writes Excel/JSON/HTML reports.

Run:

```bash
.\\.venv\\Scripts\\python.exe main.py --config projects/rezervasyon_puan_reviews/config.yaml --run-workflows --discover-wf projects/rezervasyon_puan_reviews --workflow-name rezervasyon_puan_reviews
```
````

---

### Task 2: Source Workbook Reader

**Files:**
- Create: `projects/rezervasyon_puan_reviews/workflow.py`
- Test: `projects/rezervasyon_puan_reviews/tests/test_workflow.py`

- [ ] **Step 1: Write failing reader test**

Add to `projects/rezervasyon_puan_reviews/tests/test_workflow.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from openpyxl import Workbook


MODULE_PATH = Path(__file__).resolve().parents[1] / "workflow.py"
SPEC = importlib.util.spec_from_file_location("rezervasyon_puan_reviews", MODULE_PATH)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = workflow
SPEC.loader.exec_module(workflow)


def test_read_rezervasyon_puan_records_keeps_score_count_and_link(tmp_path):
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Taksim Analiz"
    ws.cell(row=1, column=2, value="Expedia/Hotels")
    ws.cell(row=2, column=1, value="Otel Adı")
    ws.cell(row=2, column=2, value="Puan")
    ws.cell(row=2, column=3, value="Yorum")
    ws.cell(row=2, column=4, value="Link")
    ws.cell(row=3, column=1, value="The Marmara Taksim")
    ws.cell(row=3, column=2, value=9.0)
    ws.cell(row=3, column=3, value=1014)
    ws.cell(row=3, column=4, value="Git")
    ws.cell(row=3, column=4).hyperlink = "https://example.test/expedia"
    path = tmp_path / "Branches.xlsx"
    workbook.save(path)

    records = workflow.read_rezervasyon_puan_records(path, "Taksim Analiz")

    assert records == [
        {
            "id": "3:Expedia/Hotels",
            "source_row": 3,
            "hotel": "The Marmara Taksim",
            "platform": "Expedia/Hotels",
            "platform_score": 9.0,
            "platform_review_count": 1014,
            "url": "https://example.test/expedia",
            "domain": "example.test",
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest projects/rezervasyon_puan_reviews/tests/test_workflow.py::test_read_rezervasyon_puan_records_keeps_score_count_and_link -q
```

Expected: FAIL because `workflow.py` does not exist yet.

- [ ] **Step 3: Add minimal workflow and reader**

Write `projects/rezervasyon_puan_reviews/workflow.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from projects.ota_recent_reviews.workflow import OtaRecentReviewsFromExcelWorkflow


DEFAULT_INPUT = "C:/Users/Rau/Desktop/Archive/TM-57-Rezervasyon_Puan/data/Branches.xlsx"
DEFAULT_SHEET = "Taksim Analiz"
DEFAULT_JSON = "runs/rezervasyon_puan_reviews/reviews_last_30_days.json"
DEFAULT_HTML = "reports/rezervasyon_puan_reviews/reviews_last_30_days.html"
DEFAULT_XLSX = "reports/rezervasyon_puan_reviews/reviews_last_30_days.xlsx"
PLATFORM_START_COLUMN = 2
PLATFORM_WIDTH = 3
HOTEL_NAME_COLUMN = 1


class RezervasyonPuanReviewsWorkflow(OtaRecentReviewsFromExcelWorkflow):
    name = "rezervasyon_puan_reviews"
    tags = ["rpa", "excel", "browser", "reviews", "ota", "tm-57"]
    max_retries_per_record = 0

    async def setup(self):
        await super().setup()
        self.input_path = Path(self.config.variables.get("input_excel", DEFAULT_INPUT))
        self.sheet_name = self.config.variables.get("sheet", DEFAULT_SHEET)
        self.output_json = Path(self.config.variables.get("output_json", DEFAULT_JSON))
        self.output_html = Path(self.config.variables.get("output_html", DEFAULT_HTML))
        self.output_xlsx = Path(self.config.variables.get("output_excel", DEFAULT_XLSX))
        self.records = read_rezervasyon_puan_records(self.input_path, self.sheet_name)

    async def teardown(self):
        result = {
            "input_excel": str(self.input_path),
            "sheet": self.sheet_name,
            "last_30_days_window": {
                "start": self.start_date.isoformat(),
                "end": self.as_of.isoformat(),
            },
            "total_links": len(self.summary_rows),
            "processed": sum(1 for row in self.summary_rows if row["status"] == "processed"),
            "links_with_recent_reviews": sum(1 for row in self.summary_rows if row["recent_review_count"] > 0),
            "total_recent_reviews": len(self.review_rows),
            "blocked_or_empty": sum(1 for row in self.summary_rows if row.get("blocked") or row["recent_review_count"] == 0),
            "summary": self.summary_rows,
            "reviews": self.review_rows,
        }
        self.output_json.parent.mkdir(parents=True, exist_ok=True)
        self.output_html.parent.mkdir(parents=True, exist_ok=True)
        self.output_xlsx.parent.mkdir(parents=True, exist_ok=True)
        self.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        self.output_html.write_text(render_html_report(result), encoding="utf-8")
        write_review_workbook(self.output_xlsx, result)
        self.result.output_files.extend([str(self.output_json), str(self.output_html), str(self.output_xlsx)])


def read_rezervasyon_puan_records(input_path: Path, sheet_name: str) -> list[dict]:
    workbook = load_workbook(input_path, data_only=False)
    worksheet = workbook[sheet_name]
    records: list[dict] = []
    for row in range(3, worksheet.max_row + 1):
        hotel = worksheet.cell(row=row, column=HOTEL_NAME_COLUMN).value
        if not hotel:
            continue
        for platform, score_col, count_col, link_col in platform_columns(worksheet):
            link_cell = worksheet.cell(row=row, column=link_col)
            target = link_cell.hyperlink.target if link_cell.hyperlink else None
            if not target:
                continue
            records.append(
                {
                    "id": f"{row}:{platform}",
                    "source_row": row,
                    "hotel": str(hotel).strip(),
                    "platform": platform,
                    "platform_score": worksheet.cell(row=row, column=score_col).value,
                    "platform_review_count": worksheet.cell(row=row, column=count_col).value,
                    "url": target,
                    "domain": urlparse(target).netloc,
                }
            )
    return records


def platform_columns(worksheet) -> list[tuple[str, int, int, int]]:
    columns: list[tuple[str, int, int, int]] = []
    col = PLATFORM_START_COLUMN
    while col <= worksheet.max_column:
        platform = worksheet.cell(row=1, column=col).value
        if platform and str(platform).strip().lower() != "ortalama":
            columns.append((str(platform).strip(), col, col + 1, col + 2))
        col += PLATFORM_WIDTH
    return columns
```

- [ ] **Step 4: Run reader test**

Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest projects/rezervasyon_puan_reviews/tests/test_workflow.py::test_read_rezervasyon_puan_records_keeps_score_count_and_link -q
```

Expected: PASS.

---

### Task 3: Excel Report Shape

**Files:**
- Modify: `projects/rezervasyon_puan_reviews/workflow.py`
- Modify: `projects/rezervasyon_puan_reviews/tests/test_workflow.py`

- [ ] **Step 1: Write failing workbook test**

Append to `projects/rezervasyon_puan_reviews/tests/test_workflow.py`:

```python
from openpyxl import load_workbook


def test_write_review_workbook_writes_summary_and_reviews(tmp_path):
    output = tmp_path / "reviews.xlsx"
    result = {
        "last_30_days_window": {"start": "2026-05-18", "end": "2026-06-17"},
        "summary": [
            {
                "hotel": "The Marmara Taksim",
                "platform": "Expedia/Hotels",
                "platform_score": 9.0,
                "platform_review_count": 1014,
                "status": "processed",
                "fetch_status": "loaded",
                "recent_review_count": 1,
                "blocked": False,
                "url": "https://example.test/expedia",
                "final_url": "https://example.test/expedia",
                "error": "",
            }
        ],
        "reviews": [
            {
                "hotel": "The Marmara Taksim",
                "platform": "Expedia/Hotels",
                "source_row": 3,
                "domain": "example.test",
                "date": "2026-06-10",
                "reviewer": "Guest",
                "rating": "10/10",
                "title": "Great stay",
                "text": "Clean rooms and helpful staff.",
                "source_url": "https://example.test/expedia",
                "extraction_method": "playwright_body_text",
            }
        ],
    }

    workflow.write_review_workbook(output, result)

    workbook = load_workbook(output)
    assert workbook.sheetnames == ["Summary", "Reviews"]
    assert workbook["Summary"]["A3"].value == "Hotel"
    assert workbook["Summary"]["E4"].value == 1014
    assert workbook["Reviews"]["A2"].value == "The Marmara Taksim"
    assert workbook["Reviews"]["H2"].value == "Clean rooms and helpful staff."
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest projects/rezervasyon_puan_reviews/tests/test_workflow.py::test_write_review_workbook_writes_summary_and_reviews -q
```

Expected: FAIL because `write_review_workbook` is not implemented.

- [ ] **Step 3: Add workbook writer and minimal HTML**

Append to `projects/rezervasyon_puan_reviews/workflow.py`:

```python
def write_review_workbook(output_path: Path, result: dict) -> None:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary.append(["Window Start", result["last_30_days_window"]["start"], "Window End", result["last_30_days_window"]["end"]])
    summary.append([])
    summary.append([
        "Hotel",
        "Platform",
        "Platform Score",
        "Platform Review Count",
        "Recent Review Count",
        "Status",
        "Fetch Status",
        "Blocked",
        "Source URL",
        "Final URL",
        "Error",
    ])
    for row in result["summary"]:
        summary.append([
            row.get("hotel"),
            row.get("platform"),
            row.get("platform_score"),
            row.get("platform_review_count"),
            row.get("recent_review_count"),
            row.get("status"),
            row.get("fetch_status"),
            row.get("blocked"),
            row.get("url"),
            row.get("final_url"),
            row.get("error"),
        ])

    reviews = workbook.create_sheet("Reviews")
    reviews.append([
        "Hotel",
        "Platform",
        "Source Row",
        "Domain",
        "Review Date",
        "Reviewer",
        "Rating",
        "Review Text",
        "Title",
        "Source URL",
        "Extraction Method",
    ])
    for row in result["reviews"]:
        reviews.append([
            row.get("hotel"),
            row.get("platform"),
            row.get("source_row"),
            row.get("domain"),
            row.get("date"),
            row.get("reviewer"),
            row.get("rating"),
            row.get("text"),
            row.get("title"),
            row.get("source_url"),
            row.get("extraction_method"),
        ])

    for worksheet in workbook.worksheets:
        header_row = 3 if worksheet.title == "Summary" else 1
        for cell in worksheet[header_row]:
            cell.font = Font(bold=True)
        for column_cells in worksheet.columns:
            width = min(max(len(str(cell.value or "")) for cell in column_cells), 80)
            worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = max(12, width + 2)
        worksheet.freeze_panes = "A4" if worksheet.title == "Summary" else "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
    workbook.save(output_path)


def render_html_report(result: dict) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Rezervasyon Puan Reviews</title></head>"
        "<body>"
        f"<h1>Rezervasyon Puan Reviews</h1>"
        f"<p>{result['last_30_days_window']['start']} to {result['last_30_days_window']['end']}</p>"
        f"<p>Total links: {result['total_links']} | Recent reviews: {result['total_recent_reviews']}</p>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run workbook tests**

Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest projects/rezervasyon_puan_reviews/tests/test_workflow.py -q
```

Expected: PASS.

---

### Task 4: Project Layout and Harness Checks

**Files:**
- Modify: `tests/test_project_layout.py`

- [ ] **Step 1: Add the project to layout tests**

In `tests/test_project_layout.py`, add the project name to the existing `PROJECTS` tuple:

```python
PROJECTS = (
    "example_data_verification",
    "operaRezervasyon",
    "ota_link_swarm",
    "ota_recent_reviews",
    "rezervasyon_puan_reviews",
    "rpa_challenge",
    "trip_com_reviews",
)
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest projects/rezervasyon_puan_reviews/tests/test_workflow.py tests/test_project_layout.py -q
```

Expected: PASS.

- [ ] **Step 3: Audit workflow descriptor**

Run:

```powershell
.\\.venv\\Scripts\\python.exe main.py --audit-workflow projects/rezervasyon_puan_reviews/workflows/main.yaml
```

Expected: audit completes without missing required workflow metadata.

---

### Task 5: Safe Real Preflight

**Files:**
- Runtime outputs only:
  - `runs/rezervasyon_puan_reviews/reviews_last_30_days.json`
  - `reports/rezervasyon_puan_reviews/reviews_last_30_days.html`
  - `reports/rezervasyon_puan_reviews/reviews_last_30_days.xlsx`

- [ ] **Step 1: Run the automation**

Run:

```powershell
.\\.venv\\Scripts\\python.exe main.py --config projects/rezervasyon_puan_reviews/config.yaml --run-workflows --discover-wf projects/rezervasyon_puan_reviews --workflow-name rezervasyon_puan_reviews
```

Expected: workflow visits each source URL from `Branches.xlsx` and writes JSON, HTML, and Excel outputs.

- [ ] **Step 2: Verify Excel output exists and has rows**

Run:

```powershell
@'
from pathlib import Path
from openpyxl import load_workbook

path = Path("reports/rezervasyon_puan_reviews/reviews_last_30_days.xlsx")
assert path.exists(), path
workbook = load_workbook(path)
assert workbook["Summary"].max_row >= 3
assert workbook["Reviews"].max_row >= 1
print({"summary_rows": workbook["Summary"].max_row, "review_rows": workbook["Reviews"].max_row})
'@ | .\\.venv\\Scripts\\python.exe -
```

Expected: printed row counts. `Reviews` may contain only the header if public sites expose no parseable last-30-day reviews during this run; that is a valid evidence-backed result.

- [ ] **Step 3: Record blockers from evidence**

If a site blocks automation, keep the row as `blocked_or_empty` or `failed` in `Summary`. Do not retry non-idempotent actions and do not bypass login, CAPTCHA, or bot checks.

---

## Self-Review

- Spec coverage: reads hotel/platform links from Excel, visits each OTA source, filters last 30 days through existing extractor, writes Excel output.
- Deliberate skips: AI analysis, WhatsApp, CRM, Google Sheets, and old Canvas JSON migration.
- Selector quality: first pass uses existing public HTML/body-text extraction. If a platform fails with parseable UI but no text extraction, run `projects/ota_link_swarm` as a separate repair pass for that platform.
- Success check coverage: descriptor has explicit postconditions; tests cover source parsing and workbook writing; real preflight verifies output artifacts.
