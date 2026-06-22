# rezervasyon_puan_reviews

This project currently has no implemented business workflow.

The YAML runner is the only supported runtime. `workflows/main.yaml` is an audit-only/no-op descriptor until real YAML workflow steps are added.

Audit the descriptor:

```powershell
.\.venv\Scripts\python.exe main.py --audit-workflow projects/rezervasyon_puan_reviews/workflows/main.yaml
```

Current behavior:

- no browser/Excel review extraction runs
- no review JSON/HTML/XLSX business reports are produced
- the descriptor exists only to keep project metadata auditable
