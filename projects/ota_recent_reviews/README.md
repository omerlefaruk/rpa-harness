# ota_recent_reviews

Excel-driven recent OTA review extraction workflow.

- Workflow code: `workflow.py`
- Config: `config.yaml`
- Project workflow descriptor: `workflows/main.yaml`
- Tests: `tests/test_workflow.py`

Run:

```bash
python main.py --config projects/ota_recent_reviews/config.yaml --run-workflows --discover-wf projects/ota_recent_reviews --workflow-name ota_recent_reviews_from_excel
```
