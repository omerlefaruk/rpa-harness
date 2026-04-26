# Model Mapping

## Task-Type → Model Assignment

Configured in `.agents/config/agents.yaml`. Default mapping:

| Model Key | Provider | Default Model | Use Case |
|---|---|---|---|
| `fast` | openai-compatible | gpt-4o-mini | Explorer, Selector, UIA-tree, Memory search |
| `powerful` | openai-compatible | gpt-4o | Planner, Orchestrator, Agent decisions |
| `vision` | openai-compatible | gpt-4o | Screenshot analysis, element detection |

## Model Properties

```yaml
fast:
  temperature: 0.1    # Deterministic for data extraction
  max_tokens: 4000     # Compact results

powerful:
  temperature: 0.2    # Slightly creative for planning
  max_tokens: 8000     # Room for complex plans

vision:
  temperature: 0.1    # Precise visual analysis
  max_tokens: 4000     # Structured JSON responses
```

## Override Hierarchy

1. Environment variables (`OPENAI_API_KEY`, `OPENAI_API_BASE`)
2. YAML config file (`config/default.yaml`)
3. CLI arguments (`--vision-model`, `--agent-model`)
4. Default fallback (built-in values)
