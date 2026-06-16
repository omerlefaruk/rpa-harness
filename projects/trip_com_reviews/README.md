# trip_com_reviews

Excel-driven Trip.com recent review extraction workflow.

- Workflow code: `workflow.py`
- Config: `config.yaml`
- Project workflow descriptor: `workflows/main.yaml`
- Tests: `tests/test_workflow.py`

Run:

```bash
python main.py --config projects/trip_com_reviews/config.yaml --run-workflows --discover-wf projects/trip_com_reviews --workflow-name trip_com_reviews_from_excel
```
