---
name: excel-workflows
description: >
  Excel-driven RPA workflow patterns. Read input Excel,
  process each row against web/desktop systems,
  write mismatch results to output Excel.
  Use when creating data-driven automation workflows.
hooks: "preflight, compliance, validation, reporting"
---

# Excel Workflows

## Pattern: Read → Process → Report

```python
from harness import RPAWorkflow, ExcelHandler

class DataVerificationWorkflow(RPAWorkflow):
    async def setup(self):
        self.input = ExcelHandler(self.config.variables["input_file"])
        self.output = ExcelHandler(self.config.variables["output_file"])
        self.output.write_rows(sheet="Mismatches", headers=["ID", "Reason", "Expected", "Actual"])

    def get_records(self):
        for row in self.input.iter_rows(sheet="Sheet1", header_row=1,
                                         columns=["ID", "Name", "Value"]):
            yield {"id": row.get("ID"), "name": row.get("Name"), "value": row.get("Value")}

    async def process_record(self, record):
        # Look up in system, compare values
        return {"status": "passed" if match else "failed", ...}

    async def on_mismatch(self, record, reason, details=None):
        self.output.append_row(sheet="Mismatches", mapping={...}, headers=[...])
```

## Column Validation

```python
assert self.input.validate_columns(sheet="Sheet1",
    expected_columns=["ID", "Name", "Value"])
```
