# roi-harness

Thin npm launcher for the Python rpa-harness runtime.

```bash
npx roi-harness init
npx roi-harness validate workflows/example.yaml
npx roi-harness mcp
```

The MCP bridge exposes governed workflow tools only: validate, preflight, run, run inspection, report lookup, and selector repair. No arbitrary shell tool is provided.
