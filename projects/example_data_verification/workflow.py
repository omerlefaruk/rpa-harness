"""
Example RPA workflow — data verification pattern.
"""

from harness import RPAWorkflow, ExcelHandler


class ExampleDataVerificationWorkflow(RPAWorkflow):
    name = "example_data_verification"
    tags = ["rpa", "excel", "example"]

    async def setup(self):
        self.log("=== Data Verification Workflow ===")

        step = self.step("Initialize Excel handlers")
        self.input_excel = ExcelHandler(
            self.config.variables.get("input_excel", "./data/input.xlsx")
        )
        self.output_excel = ExcelHandler(
            self.config.variables.get("output_excel", "./reports/output.xlsx")
        )
        self.output_excel.write_rows(
            sheet="Mismatches",
            headers=["ID", "Reason", "Expected Value", "Actual Value"],
        )
        self.step_done(step)

    def get_records(self):
        yield {"id": "REC001", "name": "Test Item", "expected_price": 100}
        yield {"id": "REC002", "name": "Test Item 2", "expected_price": 200}

    async def process_record(self, record):
        system_price = record["expected_price"]  # Replace with actual lookup

        if system_price != record["expected_price"]:
            return {
                "status": "failed",
                "reason": "Price mismatch",
                "details": {
                    "excel_value": record["expected_price"],
                    "system_value": system_price,
                },
            }
        return {"status": "passed"}

    async def on_mismatch(self, record, reason, details=None):
        details = details or {}
        self.output_excel.append_row(
            sheet="Mismatches",
            mapping={
                "ID": record.get("id"),
                "Reason": reason,
                "Expected Value": details.get("excel_value", ""),
                "Actual Value": details.get("system_value", ""),
            },
            headers=["ID", "Reason", "Expected Value", "Actual Value"],
        )

    async def teardown(self):
        self.output_excel.save()
        self.result.output_files.append(str(self.output_excel.file_path))
        self.log("Workflow complete")
