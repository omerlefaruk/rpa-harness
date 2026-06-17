# ota_link_swarm

Excel-driven OTA link selector-swarm workflow.

- Workflow code: `workflow.py`
- Config: `config.yaml`
- Project workflow descriptor: `workflows/main.yaml`
- Tests: `tests/test_workflow.py`

Run:

```bash
python main.py --config projects/ota_link_swarm/config.yaml --run-workflows --discover-wf projects/ota_link_swarm --workflow-name ota_link_swarm_from_excel
```
