# trip_com_reviews

Excel-driven Trip.com recent review extraction workflow.

- Config: `config.yaml`
- Project workflow descriptor: `workflows/main.yaml`

Run:

```bash
python main.py --audit-workflow projects/trip_com_reviews/workflows/main.yaml
python main.py --run-yaml projects/trip_com_reviews/workflows/main.yaml
```
