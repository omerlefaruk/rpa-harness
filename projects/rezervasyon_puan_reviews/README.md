# rezervasyon_puan_reviews

Reads hotel/platform links from `Branches.xlsx`, visits each OTA review source, extracts reviews from the last 30 days, and writes Excel/JSON/HTML reports.

Default mode is `full`: Expedia runs through a dedicated Chrome CDP profile; the other platforms run through the standard headless path. Results are merged and deduped.

Run:

```powershell
.\.venv\Scripts\python.exe main.py --run-yaml projects/rezervasyon_puan_reviews/workflows/main.yaml
```

Modes:

- `full`: platform-specific best path, timestamped raw JSON, merged Excel.
- `fast`: one pass in workbook order.
- `debug`: same as `full`, but saves evidence for every processed row.
- `headless`: force standard headless browser.
- `cdp`: force Chrome CDP profile.

Outputs:

- `reports/rezervasyon_puan_reviews/reviews_last_30_days.xlsx`
- `runs/rezervasyon_puan_reviews/reviews_last_30_days.json`
- `runs/rezervasyon_puan_reviews/raw/*.json`
- `runs/rezervasyon_puan_reviews/evidence/*`
