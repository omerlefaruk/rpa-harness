# rpa-harness workspace

Run locally:

```bash
rpa-harness --validate-yaml workflows/example.yaml
rpa-harness --preflight-yaml workflows/example.yaml
rpa-harness --run-yaml workflows/example.yaml
```

AI agents should use `.agents/config/agent_command_manifest.json` instead of arbitrary shell commands.
