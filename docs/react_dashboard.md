# React Dashboard

The React dashboard is a read-only operator UI over the local FastAPI API.
`DESIGN.md` is the visual design contract for this surface.

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

Modes:

- Monitor: top command bar, flight-deck run status, horizontal process map, live log console, decision panel, evidence wall with screenshot/GIF/log artifact previews, collapsed developer details.
- History: compact run board with status rails.
- Builder: builder sessions and draft status.

The dashboard intentionally avoids separate tabs for raw records, failures,
selectors, repair packets, and observability JSON. Those stay in the selected
run context and raw JSON is only shown inside collapsed developer details.

Limitations: the dashboard is local, read-only, and has no multi-user authentication or execution controls.
