# Live UI

Live monitoring reads `timeline.jsonl`. The runner remains the execution engine.

Endpoints:

- `GET /api/runs/{run_id}/events` returns polling events
- `GET /api/runs/{run_id}/events?after_id=123` returns events after a cursor
- `GET /api/runs/{run_id}/events?stream=true` streams Server-Sent Events

CLI:

```bash
python main.py --live-tail RUN_ID
python main.py --serve --port 8080
```

The live surface is read-only. It does not approve gates, retry records, or execute workflow controls.
