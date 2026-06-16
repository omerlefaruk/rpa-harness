# example_data_verification

Python RPAWorkflow example for Excel-style data verification.

- Workflow code: `workflow.py`
- Config: `config.yaml`
- Project workflow descriptor: `workflows/main.yaml`
- Tests: `tests/test_workflow.py`

Run:

```bash
python main.py --config projects/example_data_verification/config.yaml --run-workflows --discover-wf projects/example_data_verification --workflow-name example_data_verification
```
