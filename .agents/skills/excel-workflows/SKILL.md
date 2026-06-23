---
name: excel-workflows
description: >
  Use when creating Excel-driven YAML RPA workflows that read workbook rows,
  validate sheet/column assumptions, process rows through browser/desktop/API
  steps, and write run artifacts or reports.
hooks: "preflight, compliance, validation, reporting"
---

# Excel Workflows

YAML is the only supported runtime. Do not create Python class workflow subclasses.

## Pattern: Validate → Read → Process → Report

```yaml
id: workbook_check
name: Workbook Check
version: "0.1.0"
type: excel
inputs:
  input_excel: ./data/input.xlsx
  sheet: Sheet1
steps:
  - id: read_rows
    action:
      type: excel.read
      path: ${inputs.input_excel}
      sheet: ${inputs.sheet}
      output: rows
    success_check:
      - type: sheet_exists
        value: ${inputs.sheet}

  - id: process_rows
    action:
      type: no_op
    success_check:
      - type: always_pass
```

Use terminal checks:

```powershell
.\.venv\Scripts\python.exe main.py --audit-workflow projects/<project>/workflows/main.yaml
.\.venv\Scripts\python.exe main.py --run-yaml projects/<project>/workflows/main.yaml
.\.venv\Scripts\python.exe main.py --runs-show RUN_ID
```

Keep workbook parsing explicit in YAML inputs and success checks. Add Python only when a real action type is missing and the YAML runner needs it.
