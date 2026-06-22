---
name: search-to-rpa-workflow
description: Convert a searched or described business process into a deterministic rpa-harness workflow with evidence, verification, and repair guidance.
---

# Search to RPA Workflow

Use this skill when turning a user request, researched process, target website, desktop app, API, or Excel task into an rpa-harness workflow.

## Required approach

1. Start with task intake: goal, target system, input files, output expectations, secret names, risky actions, and success criteria.
2. Search or inspect only enough to identify the deterministic automation path.
3. Save findings in a dedicated harness artifact rather than free-form scratch notes.
4. Check existing run artifacts for prior selectors, workflows, failures, and repair evidence before creating new assumptions.
5. Use browser selector swarm for browser targets when selectors are unknown or likely to be brittle.
6. Use UIA/Win32 inspection for desktop targets before image/OCR/coordinate fallbacks.
7. Draft workflow phases and steps with success checks on every step.
8. Mark side effects, retry policy, idempotency keys, weak selectors, and human gates.
9. Run preflight and safe dry-runs before any risky external write.
10. Use reports, evidence bundles, and repair packets to fix failures.

## Hardening requirements

- Action execution is not success; explicit success checks are required.
- Secret values must not be hardcoded, logged, stored in reports, screenshots metadata, or repair artifacts.
- Evidence must support claims. Use run artifacts, not guesses.
- Risky actions such as submit, upload, delete, send, payment, and irreversible update require approval or explicit policy.
- Do not auto-retry non-idempotent external writes.

## Selector strategy

Browser priority:

data-testid → role/name → label → placeholder → text → stable id → CSS → XPath

Desktop priority:

automation_id → name/control_type → class/control_type → tree path → image anchor → coordinate fallback

Coordinates are a last resort and must be relative, calibrated, logged as weak, and verified after action.

## Output

When producing or repairing a workflow, return:

1. Workflow draft path.
2. Discovery artifacts.
3. Selector quality summary.
4. Success check coverage.
5. Risky steps and human gates.
6. Preflight/dry-run result.
7. Unresolved questions.
8. Suggested next command.
