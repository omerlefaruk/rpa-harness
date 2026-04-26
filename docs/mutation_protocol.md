# Mutation Protocol

Controls how the agent may improve the harness, skills, rules, and memory system.

## Protected Areas

- `AGENTS.md`
- `.agents/rules/`
- `.agents/skills/`
- `harness/core/`
- `harness/orchestrator.py`
- `harness/memory/`
- `harness/resilience/`
- `docs/credential_policy.md`
- `docs/memory_policy.md`
- `docs/mutation_protocol.md`

## Required Mutation Flow

Before editing a protected area, produce:

```json
{
  "mutation_request": {
    "target_files": [],
    "reason": "",
    "observed_failure_or_limitation": "",
    "evidence_path": "",
    "risk_level": "low | medium | high",
    "rollback_plan": "",
    "tests_to_run": []
  }
}
```

## Patch Requirements

A mutation is allowed only when:
1. There is a concrete failure, limitation, or repeated pattern
2. The target file is the smallest reasonable place to fix it
3. Tests are added or updated
4. The patch can be rolled back
5. The final report includes evidence

## Self-Improvement Categories

### Allowed Automatically
- Add new workflow example
- Add selector candidate to cache after successful validation
- Add error observation to runtime memory
- Add test for existing bug
- Improve documentation after implementation

### Requires Review
- Change memory policy
- Change credential policy
- Change mutation protocol
- Change core orchestrator behavior
- Change retry strategy globally
- Add a new Skill
- Modify AGENTS.md
- Modify protected harness abstractions

### Forbidden
- Store raw credentials
- Disable verification checks to make a run pass
- Remove failure evidence capture
- Replace semantic selectors with coordinates (unless marked as last resort)
- Suppress errors without reporting them
- Delete tests to pass the suite
