# OKF Knowledge Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OKF v0.1 knowledge bundle for `rpa-harness` and automate validation through scripts, hooks, AGENTS rules, and the existing agent command manifest.

**Architecture:** Store the bundle as markdown under `docs/okf`. Add one stdlib/PyYAML script that validates frontmatter, reserved files, indexes, and logs, and can regenerate `index.md` files. Wire the script into tests, a pre-commit hook, and the existing agent/copilot command manifest.

**Tech Stack:** Python, PyYAML already in the repo, pytest, git hooks, markdown files.

---

## File Structure

- Create: `scripts/okf.py`
  - Validate OKF bundles and regenerate directory indexes.
- Create: `tests/test_okf_bundle.py`
  - Prove validator failure cases, index generation, and real bundle conformance.
- Create: `docs/okf/index.md`
  - Root OKF index with `okf_version: "0.1"`.
- Create: `docs/okf/log.md`
  - Root update log with ISO date headings.
- Create: `docs/okf/system/rpa-harness.md`
  - Repo/system concept.
- Create: `docs/okf/interfaces/cli.md`
  - CLI concept.
- Create: `docs/okf/runtime/workflow-runner.md`
  - YAML runner concept.
- Create: `docs/okf/automation/copilot-autopilot.md`
  - Copilot/autopilot concept.
- Create: `docs/okf/agents/agent-rules.md`
  - Agent rules concept.
- Create: `.githooks/pre-commit`
  - Run OKF validation before commit.
- Modify: `.agents/config/agent_command_manifest.json`
  - Add `okf_validate` and `okf_generate_indexes`.
- Modify: `AGENTS.md`
  - Add concise OKF maintenance rules.
- Modify: `README.md`
  - Add the operator commands.

---

### Task 1: Add The Failing OKF Tests

**Files:**
- Create: `tests/test_okf_bundle.py`

- [ ] **Step 1: Write tests**

```python
from pathlib import Path

from scripts.okf import build_index_text, validate_bundle


def test_validate_bundle_rejects_concept_without_type(tmp_path):
    bundle = tmp_path / "okf"
    bundle.mkdir()
    (bundle / "bad.md").write_text("---\ntitle: Bad\n---\n\nBody\n", encoding="utf-8")

    result = validate_bundle(bundle)

    assert result["status"] == "failed"
    assert any("missing required type" in error for error in result["errors"])


def test_build_index_text_groups_concepts_and_subdirectories(tmp_path):
    bundle = tmp_path / "okf"
    concepts = bundle / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "runner.md").write_text(
        "---\ntype: Component\ntitle: Runner\ndescription: Executes workflows.\n---\n\nBody\n",
        encoding="utf-8",
    )

    text = build_index_text(bundle, bundle)

    assert "* [concepts](concepts/) - OKF concepts in `concepts/`." in text


def test_repo_okf_bundle_is_conformant():
    result = validate_bundle(Path("docs/okf"))

    assert result["status"] == "passed"
    assert result["concept_count"] >= 5
    assert result["warnings"] == []
```

- [ ] **Step 2: Run failing tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_okf_bundle.py -q`

Expected: import failure because `scripts.okf` does not exist.

---

### Task 2: Implement The Minimal Validator And Index Generator

**Files:**
- Create: `scripts/okf.py`

- [ ] **Step 1: Implement**

Add:

- `parse_markdown(path)`
- `validate_bundle(root)`
- `build_index_text(root, directory)`
- CLI commands: `validate` and `generate-indexes`

Rules:

- Non-reserved `.md` files require YAML frontmatter and non-empty `type`.
- `index.md` may omit frontmatter except root `okf_version: "0.1"`.
- `log.md` date headings must match `## YYYY-MM-DD`.
- Broken markdown links are warnings only.

- [ ] **Step 2: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_okf_bundle.py -q`

Expected: tests fail only because `docs/okf` is missing.

---

### Task 3: Add The Repo OKF Bundle

**Files:**
- Create: `docs/okf/index.md`
- Create: `docs/okf/log.md`
- Create concept files listed in File Structure.

- [ ] **Step 1: Write concepts**

Each concept gets:

```yaml
---
type: Reference
title: Human title
description: One sentence.
tags: [rpa-harness]
timestamp: 2026-06-17T00:00:00Z
---
```

The body links to local repo docs and neighboring OKF concepts.

- [ ] **Step 2: Generate indexes**

Run: `.venv\Scripts\python.exe scripts/okf.py generate-indexes docs/okf`

Expected: root and subdirectory `index.md` files are created or refreshed.

- [ ] **Step 3: Validate**

Run: `.venv\Scripts\python.exe scripts/okf.py validate docs/okf`

Expected: JSON status `passed`.

---

### Task 4: Wire Automation

**Files:**
- Create: `.githooks/pre-commit`
- Modify: `.agents/config/agent_command_manifest.json`
- Modify: `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Add pre-commit hook**

The hook runs:

```bash
python scripts/okf.py validate docs/okf
python -m pytest tests/test_okf_bundle.py -q
```

It prefers `.venv/Scripts/python.exe` when present.

- [ ] **Step 2: Configure local hook path**

Run: `git config core.hooksPath .githooks`

- [ ] **Step 3: Add agent commands**

Add manifest commands:

- `okf_validate`
- `okf_generate_indexes`

- [ ] **Step 4: Add AGENTS and README rules**

State that agents changing docs, skills, workflows, or CLI surfaces must update `docs/okf`, run index generation, and validate.

---

### Task 5: Verify

Run:

```bash
.venv\Scripts\python.exe -m pytest tests/test_okf_bundle.py tests/test_autopilot.py -q
.venv\Scripts\python.exe scripts/okf.py validate docs/okf
.githooks\pre-commit
git diff --check
```

Expected:

- OKF tests pass.
- Existing autopilot manifest test still passes.
- OKF validator reports `passed`.
- Hook exits 0.
- Diff whitespace check is clean.

---

## Self-Review

- Spec coverage: concept frontmatter, reserved filenames, root version, logs, indexes, warnings for broken links, and permissive unknown fields are covered.
- Placeholder scan: no task depends on an unnamed future tool.
- Type consistency: script command names match hook, README, AGENTS, and command manifest.
