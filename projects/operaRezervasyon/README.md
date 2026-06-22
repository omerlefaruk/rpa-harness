# operaRezervasyon

OPERA Cloud reservation workbook validation and dry-run planning.

- Workflow descriptor: `workflows/main.yaml`
- Config: `config.yaml`

Run validation:

```bash
python main.py --audit-workflow projects/operaRezervasyon/workflows/main.yaml
python main.py --run-yaml projects/operaRezervasyon/workflows/main.yaml
```
