# operaRezervasyon

OPERA Cloud reservation workbook validation and dry-run planning.

- Workflow descriptor: `workflows/main.yaml`
- Python workflow code: `workflow.py`
- Config: `config.yaml`
- Tests: `tests/test_workflow.py`

Run validation:

```bash
python main.py --audit-workflow projects/operaRezervasyon/workflows/main.yaml
python -m pytest projects/operaRezervasyon/tests/test_workflow.py
```
