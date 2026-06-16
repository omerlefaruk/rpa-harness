# rezervasyon_puan_reviews

Reads hotel/platform links from `Branches.xlsx`, visits each OTA review source, extracts reviews from the last 30 days, and writes Excel/JSON/HTML reports.

Run:

```bash
.\\.venv\\Scripts\\python.exe main.py --config projects/rezervasyon_puan_reviews/config.yaml --run-workflows --discover-wf projects/rezervasyon_puan_reviews --workflow-name rezervasyon_puan_reviews
```
