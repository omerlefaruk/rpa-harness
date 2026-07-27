# Verification Rules

Action execution is not success. Every executable automation action must prove success via explicit verification unless it is an allowed no-op.

Canonical contract: `docs/verification_contract.md`.

Executable admission and verification for ActiveGraph live in `harness.automation` (proposal validation, capability ports, Verification Result events). Do not re-implement verification policy in skills.
