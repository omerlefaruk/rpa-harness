---
name: search-to-rpa-workflow
description: Convert a described process into an ActiveGraph proposal, not YAML.
---

# Search to automation

1. Capture Intent (capabilities, no ambiguity).
2. Gather Discovery Evidence (selectors verified).
3. Build AutomationProposal JSON for `validate_proposal` / register.
4. Never emit YAML workflow definitions.

Canonical lifecycle: `rpa-harness-automation-builder`.
