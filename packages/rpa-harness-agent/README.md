# @rpa-harness/agent

Thin npm launcher for the Python rpa-harness runtime.

```bash
npx @rpa-harness/agent init
npx @rpa-harness/agent validate workflows/example.yaml
npx @rpa-harness/agent mcp
```

The MCP bridge exposes governed workflow tools only: validate, preflight, run, run inspection, report lookup, and selector repair. No arbitrary shell tool is provided.
