# Mutation Protocol Rules

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

## Required Before Editing Protected Areas

1. State why the edit is necessary
2. Reproduce the failure or limitation
3. Add or update a test
4. Apply the smallest patch
5. Run tests
6. Summarize the evidence

## Self-Improvement Gate

No self-improvement enters the harness unless:
1. The failure is reproduced
2. The root cause is stated
3. A test is added or updated
4. The test fails before the patch
5. The test passes after the patch
6. The change is logged
7. The memory update is evidence-based

## Allowed / Requires Review / Forbidden

See `docs/mutation_protocol.md` for full categories.
