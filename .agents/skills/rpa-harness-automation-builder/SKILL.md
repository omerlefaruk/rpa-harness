# rpa-harness Automation Builder Skill

Use this skill when creating, inspecting, repairing, or improving an automation with rpa-harness.

## Core principle

Do not guess automation behavior. Build deterministic workflows from target inspection, explicit success checks, redacted evidence, and operator-approved risky actions.

## Standard flow

1. Understand the task, target, inputs, outputs, secrets, risky actions, and success criteria.
2. Inspect the target before selecting actions or selectors.
3. Generate selector/action candidates with scores and evidence.
4. Draft workflow phases and steps.
5. Add success checks to every step.
6. Mark side effects, retryability, idempotency, weak selectors, and human gates.
7. Run preflight and safe dry-runs.
8. Pause before external writes.
9. Read evidence bundles, timeline, records, report, and repair packets when debugging.
10. Repair from evidence, not assumptions.

## Browser selector priority

1. data-testid
2. role/name
3. label
4. placeholder
5. text
6. stable id
7. CSS
8. XPath

## Desktop selector priority

1. automation_id
2. name/control_type
3. class/control_type
4. tree path
5. image anchor
6. coordinate fallback

## Legacy desktop fallback

For old desktop apps with weak/no UIA, try Win32, menus, keyboard navigation, clipboard, import/export, image anchors, OCR verification, then calibrated relative coordinates as the last resort.

## Evidence to inspect

- run_manifest.json
- timeline.jsonl
- records.jsonl
- evidence_bundle.json
- screenshot/DOM/UIA/API artifacts
- selector_evidence.json
- repair_packet.json or repair_packet.md
- report.html

## Never do

- Do not hardcode or expose secret values.
- Do not generate action-only steps.
- Do not auto-submit, delete, pay, upload, or send without approval/policy.
- Do not auto-retry non-idempotent external writes.
- Do not use coordinates when DOM/UIA/API/keyboard/menu strategies are available.
