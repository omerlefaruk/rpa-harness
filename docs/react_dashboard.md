# React Dashboard

The React dashboard is a read-only operator UI over the local FastAPI API.

Build:

```bash
cd frontend
npm install
npm run build
```

Serve API and built dashboard:

```bash
python main.py --serve --port 8080
```

When `frontend/dist` exists, the FastAPI dashboard mounts it at `/app`.

Pages:

- Runs
- Run Detail
- Live
- Workflow
- Records
- Failures
- Evidence
- Selectors
- Repair Packets
- Summary
- Builders

Limitations: the dashboard is local, read-only, and has no multi-user authentication or execution controls.
