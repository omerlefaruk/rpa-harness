---
name: selector-strategies
description: Selector priority ladders matching ActiveGraph capability executables.
---

# Selector strategies

Executable priority is enforced in `harness.automation.capabilities` and repair
validation. This skill is guidance only.

## Browser

1. role
2. label
3. test_id
4. css (weak — requires verified=true + approval for writes)
5. xpath (weak)
6. coordinate (weak)

## Desktop

1. automation_id
2. name
3. class
4. tree_path
5. image (weak)
6. coordinate (weak)

Weak strategies without verification fail closed at proposal/repair admission.
Canonical authoring: `rpa-harness-automation-builder`.
