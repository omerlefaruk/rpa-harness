# rpa_challenge

RPA Challenge public-form, shortest-path, and OCR workflow project.

- YAML workflow: `workflows/main.yaml`
- Python workflows: `shortest_path.py`, `ocr.py`
- Config: `config.yaml`
- Tests: `tests/test_workflow.py`

Run validation:

```bash
python main.py --audit-workflow projects/rpa_challenge/workflows/main.yaml
python -m pytest projects/rpa_challenge/tests/test_workflow.py
```
