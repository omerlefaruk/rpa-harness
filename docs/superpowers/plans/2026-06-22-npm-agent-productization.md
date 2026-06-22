# npm Agent Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship rpa-harness as a local, installable product that users can run with `npx @rpa-harness/agent`, connect to an AI agent, and execute deterministic workflows from a project folder.

**Architecture:** Keep Python as the real automation runtime. Add a thin npm package that creates an isolated local Python runtime, initializes a workspace, and exposes a governed agent bridge over the existing allowlisted command manifest. The AI agent never receives arbitrary shell access; it calls explicit tools that map to validated rpa-harness commands and evidence artifacts.

**Tech Stack:** Python packaging with `pyproject.toml`, stdlib `venv`, Node/npm package with a `bin` launcher, MCP stdio bridge with a minimal dependency on the official MCP SDK, existing FastAPI dashboard, existing `.agents/config/agent_command_manifest.json`, pytest, Node `node:test`.

---

## File Structure

- Modify `pyproject.toml` — expose the Python CLI as an installed console script and include templates.
- Create `harness/cli.py` — package-owned CLI entrypoint; `main.py` becomes a compatibility shim.
- Modify `main.py` — delegate to `harness.cli.run()` so old commands still work.
- Create `harness/product_init.py` — initialize a consumer workspace from templates.
- Create `harness/templates/workspace/` — minimal workflow, config, agent manifest, README, and folder placeholders.
- Create `tests/test_product_init.py` — prove workspace init creates the expected safe folders/files.
- Create `tests/test_cli_entrypoint.py` — prove installed-style CLI help and init paths work.
- Create `packages/rpa-harness-agent/package.json` — npm package metadata and bin command.
- Create `packages/rpa-harness-agent/bin/rpa-harness-agent.js` — Node launcher for `init`, `serve`, `mcp`, and pass-through safe commands.
- Create `packages/rpa-harness-agent/lib/python-runtime.js` — local `.rpa-harness/venv` creation and Python command resolution.
- Create `packages/rpa-harness-agent/lib/commands.js` — wrapper around allowlisted command names.
- Create `packages/rpa-harness-agent/lib/mcp-server.js` — MCP tools backed by allowlisted commands.
- Create `packages/rpa-harness-agent/test/*.test.js` — Node tests using `node:test`.
- Modify `.github/workflows/*` or create `.github/workflows/product-package.yml` — build Python wheel, npm pack, and run smoke tests.
- Modify `README.md` — add product install quickstart.
- Modify `docs/okf/*` only if the CLI/package/workspace contract becomes durable repo knowledge.

---

## Task 1: Package the Python CLI properly

**Files:**
- Create: `harness/cli.py`
- Modify: `main.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli_entrypoint.py`

- [ ] **Step 1: Write failing CLI entrypoint tests**

```python
# tests/test_cli_entrypoint.py
import subprocess
import sys


def test_python_module_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "RPA Harness" in result.stdout
    assert "--run-yaml" in result.stdout
```

- [ ] **Step 2: Run test and verify it fails**

```bash
pytest tests/test_cli_entrypoint.py -v
```

Expected: FAIL because `harness.cli` does not exist.

- [ ] **Step 3: Move CLI ownership into the package**

Create `harness/cli.py` by moving the current `main.py` CLI code into it. Keep the async function named `main()` and add:

```python
def run() -> None:
    configure_console_encoding()
    asyncio.run(main())


if __name__ == "__main__":
    run()
```

Change `main.py` to a compatibility shim:

```python
#!/usr/bin/env python3
from harness.cli import run


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Add a console script**

In `pyproject.toml`:

```toml
[project.scripts]
rpa-harness = "harness.cli:run"
```

- [ ] **Step 5: Verify**

```bash
pytest tests/test_cli_entrypoint.py -v
python main.py --help
python -m harness.cli --help
```

Expected: all pass and both old/new command shapes print the same CLI help.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml main.py harness/cli.py tests/test_cli_entrypoint.py
git commit -m "feat: package rpa harness cli"
```

---

## Task 2: Add workspace initialization

**Files:**
- Create: `harness/product_init.py`
- Create: `harness/templates/workspace/README.md`
- Create: `harness/templates/workspace/workflows/example.yaml`
- Create: `harness/templates/workspace/config/default.yaml`
- Create: `harness/templates/workspace/.agents/config/agent_command_manifest.json`
- Modify: `harness/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_product_init.py`

- [ ] **Step 1: Write failing workspace init test**

```python
# tests/test_product_init.py
from pathlib import Path

from harness.product_init import init_workspace


def test_init_workspace_creates_agent_ready_folder(tmp_path: Path):
    init_workspace(tmp_path)

    assert (tmp_path / "workflows" / "example.yaml").exists()
    assert (tmp_path / "config" / "default.yaml").exists()
    assert (tmp_path / ".agents" / "config" / "agent_command_manifest.json").exists()
    assert (tmp_path / "runs").is_dir()
    assert (tmp_path / "reports").is_dir()
```

- [ ] **Step 2: Run test and verify it fails**

```bash
pytest tests/test_product_init.py -v
```

Expected: FAIL because `harness.product_init` does not exist.

- [ ] **Step 3: Implement minimal initializer**

```python
# harness/product_init.py
from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path


def init_workspace(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    template_root = files("harness.templates.workspace")

    for item in template_root.rglob("*"):
        relative = item.relative_to(template_root)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            with item.open("rb") as source:
                with destination.open("wb") as output:
                    shutil.copyfileobj(source, output)

    for folder in ("runs", "reports", "builder_sessions"):
        (target / folder).mkdir(exist_ok=True)
```

- [ ] **Step 4: Add CLI flag**

In `harness/cli.py`, add:

```python
parser.add_argument("--init-workspace", help="Initialize an agent-ready rpa-harness workspace")
```

In command handling:

```python
if args.init_workspace:
    from harness.product_init import init_workspace

    init_workspace(Path(args.init_workspace))
    print(f"Initialized rpa-harness workspace at {Path(args.init_workspace).resolve()}")
    return
```

- [ ] **Step 5: Include templates in the wheel**

In `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"harness.templates.workspace" = ["**/*"]
```

Add empty `__init__.py` files under:

```text
harness/templates/__init__.py
harness/templates/workspace/__init__.py
```

- [ ] **Step 6: Verify**

```bash
pytest tests/test_product_init.py tests/test_cli_entrypoint.py -v
python -m harness.cli --init-workspace .pytest_tmp/product_workspace
python -m harness.cli --validate-yaml .pytest_tmp/product_workspace/workflows/example.yaml
```

Expected: workspace is created and example workflow validates.

- [ ] **Step 7: Commit**

```bash
git add harness/product_init.py harness/templates pyproject.toml harness/cli.py tests/test_product_init.py
git commit -m "feat: initialize agent workspace"
```

---

## Task 3: Create the npm launcher package

**Files:**
- Create: `packages/rpa-harness-agent/package.json`
- Create: `packages/rpa-harness-agent/bin/rpa-harness-agent.js`
- Create: `packages/rpa-harness-agent/lib/python-runtime.js`
- Test: `packages/rpa-harness-agent/test/python-runtime.test.js`

- [ ] **Step 1: Write failing Node runtime test**

```js
// packages/rpa-harness-agent/test/python-runtime.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { runtimePaths } from "../lib/python-runtime.js";

test("runtime paths stay inside the workspace", () => {
  const paths = runtimePaths("/tmp/example-product");

  assert.equal(paths.root, "/tmp/example-product/.rpa-harness");
  assert.match(paths.python, /\.rpa-harness/);
});
```

- [ ] **Step 2: Create npm package metadata**

```json
{
  "name": "@rpa-harness/agent",
  "version": "0.1.0",
  "type": "module",
  "bin": {
    "rpa-harness-agent": "./bin/rpa-harness-agent.js"
  },
  "scripts": {
    "test": "node --test"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  },
  "files": [
    "bin",
    "lib",
    "README.md"
  ]
}
```

- [ ] **Step 3: Implement local Python runtime path resolution**

```js
// packages/rpa-harness-agent/lib/python-runtime.js
import path from "node:path";
import process from "node:process";

export function runtimePaths(cwd = process.cwd()) {
  const root = path.join(cwd, ".rpa-harness");
  const isWindows = process.platform === "win32";

  return {
    root,
    venv: path.join(root, "venv"),
    python: isWindows
      ? path.join(root, "venv", "Scripts", "python.exe")
      : path.join(root, "venv", "bin", "python"),
  };
}
```

- [ ] **Step 4: Implement launcher skeleton**

```js
#!/usr/bin/env node
// packages/rpa-harness-agent/bin/rpa-harness-agent.js
import { spawnSync } from "node:child_process";
import process from "node:process";
import { runtimePaths } from "../lib/python-runtime.js";

const [command, ...args] = process.argv.slice(2);
const paths = runtimePaths();

if (!command || command === "--help") {
  console.log("Usage: rpa-harness-agent <init|serve|mcp|run> [args]");
  process.exit(0);
}

function runPython(pythonArgs) {
  const result = spawnSync(paths.python, pythonArgs, { stdio: "inherit" });
  process.exit(result.status ?? 1);
}

if (command === "init") {
  runPython(["-m", "venv", paths.venv]);
}

if (command === "serve") {
  runPython(["-m", "harness.cli", "--serve", "--port", args[0] ?? "8080"]);
}

if (command === "run") {
  runPython(["-m", "harness.cli", ...args]);
}

console.error(`Unknown command: ${command}`);
process.exit(2);
```

- [ ] **Step 5: Verify**

```bash
cd packages/rpa-harness-agent
npm test
npm pack --dry-run
```

Expected: tests pass and package contains only `bin`, `lib`, and README.

- [ ] **Step 6: Commit**

```bash
git add packages/rpa-harness-agent
git commit -m "feat: add npm agent launcher"
```

---

## Task 4: Make `npx init` install and initialize end-to-end

**Files:**
- Modify: `packages/rpa-harness-agent/bin/rpa-harness-agent.js`
- Modify: `packages/rpa-harness-agent/lib/python-runtime.js`
- Test: `packages/rpa-harness-agent/test/init-command.test.js`

- [ ] **Step 1: Write failing command test**

```js
// packages/rpa-harness-agent/test/init-command.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { buildPythonInstallArgs } from "../lib/python-runtime.js";

test("python install uses local editable source in development", () => {
  const args = buildPythonInstallArgs({ packageSource: "../../.." });

  assert.deepEqual(args, ["-m", "pip", "install", "-e", "../../.."]);
});
```

- [ ] **Step 2: Implement install argument helper**

```js
export function buildPythonInstallArgs({ packageSource = "rpa-harness" } = {}) {
  return ["-m", "pip", "install", packageSource === "rpa-harness" ? "--upgrade" : "-e", packageSource];
}
```

Refactor if needed so published installs use:

```bash
python -m pip install --upgrade rpa-harness
```

and repo-local development uses:

```bash
RPA_HARNESS_PYTHON_SOURCE=../../.. npx @rpa-harness/agent init
```

- [ ] **Step 3: Complete `init` behavior**

`init` should:

1. Create `.rpa-harness/venv`.
2. Install the Python package.
3. Run `python -m harness.cli --init-workspace <cwd>`.
4. Print the next command: `npx @rpa-harness/agent serve`.

- [ ] **Step 4: Verify with a temp folder**

```bash
mkdir .pytest_tmp/npm-product-smoke
cd .pytest_tmp/npm-product-smoke
node ../../packages/rpa-harness-agent/bin/rpa-harness-agent.js init
node ../../packages/rpa-harness-agent/bin/rpa-harness-agent.js run --validate-yaml workflows/example.yaml
```

Expected: workspace initializes and example workflow validates.

- [ ] **Step 5: Commit**

```bash
git add packages/rpa-harness-agent
git commit -m "feat: install runtime from npm launcher"
```

---

## Task 5: Add governed command wrappers

**Files:**
- Create: `packages/rpa-harness-agent/lib/commands.js`
- Modify: `packages/rpa-harness-agent/bin/rpa-harness-agent.js`
- Test: `packages/rpa-harness-agent/test/commands.test.js`

- [ ] **Step 1: Write failing allowlist tests**

```js
// packages/rpa-harness-agent/test/commands.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { buildHarnessArgs } from "../lib/commands.js";

test("validate workflow maps to safe harness args", () => {
  assert.deepEqual(buildHarnessArgs("validate", ["workflows/example.yaml"]), [
    "-m",
    "harness.cli",
    "--validate-yaml",
    "workflows/example.yaml",
  ]);
});

test("unknown command is rejected", () => {
  assert.throws(() => buildHarnessArgs("shell", ["rm", "-rf", "."]));
});
```

- [ ] **Step 2: Implement minimal allowlist**

```js
// packages/rpa-harness-agent/lib/commands.js
const COMMANDS = {
  validate: ["--validate-yaml"],
  preflight: ["--preflight-yaml"],
  run: ["--run-yaml"],
  "runs-list": ["--runs-list"],
  "runs-show": ["--runs-show"],
  "report-open": ["--report-open"],
  "repair-selector": ["--repair-selector"],
};

export function buildHarnessArgs(command, args) {
  const mapped = COMMANDS[command];
  if (!mapped) {
    throw new Error(`Command is not allowlisted: ${command}`);
  }
  return ["-m", "harness.cli", ...mapped, ...args];
}
```

- [ ] **Step 3: Wire launcher pass-through**

```js
if (command === "validate" || command === "preflight" || command === "run") {
  runPython(buildHarnessArgs(command, args));
}
```

- [ ] **Step 4: Verify**

```bash
cd packages/rpa-harness-agent
npm test
```

Expected: unknown commands throw; known commands map to deterministic harness args.

- [ ] **Step 5: Commit**

```bash
git add packages/rpa-harness-agent
git commit -m "feat: add governed npm commands"
```

---

## Task 6: Add the AI-agent bridge through MCP

**Files:**
- Create: `packages/rpa-harness-agent/lib/mcp-server.js`
- Modify: `packages/rpa-harness-agent/bin/rpa-harness-agent.js`
- Test: `packages/rpa-harness-agent/test/mcp-tools.test.js`

- [ ] **Step 1: Define MCP tools**

Expose only these tools first:

```text
validate_workflow(workflow_path)
preflight_workflow(workflow_path)
run_workflow(workflow_path)
list_runs()
show_run(run_id)
open_report(run_id)
repair_selector(run_dir)
```

No shell tool. No arbitrary command tool.

- [ ] **Step 2: Write failing MCP tool mapping test**

```js
// packages/rpa-harness-agent/test/mcp-tools.test.js
import test from "node:test";
import assert from "node:assert/strict";
import { toolToCommand } from "../lib/mcp-server.js";

test("run_workflow maps to the allowlisted run command", () => {
  assert.deepEqual(toolToCommand("run_workflow", { workflow_path: "workflows/example.yaml" }), {
    command: "run",
    args: ["workflows/example.yaml"],
  });
});
```

- [ ] **Step 3: Implement tool-to-command mapping**

```js
export function toolToCommand(tool, input) {
  if (tool === "validate_workflow") return { command: "validate", args: [input.workflow_path] };
  if (tool === "preflight_workflow") return { command: "preflight", args: [input.workflow_path] };
  if (tool === "run_workflow") return { command: "run", args: [input.workflow_path] };
  if (tool === "list_runs") return { command: "runs-list", args: [] };
  if (tool === "show_run") return { command: "runs-show", args: [input.run_id] };
  if (tool === "open_report") return { command: "report-open", args: [input.run_id] };
  if (tool === "repair_selector") return { command: "repair-selector", args: [input.run_dir] };
  throw new Error(`Unknown MCP tool: ${tool}`);
}
```

- [ ] **Step 4: Implement stdio MCP server**

Use `@modelcontextprotocol/sdk` to register the tools and execute them through `buildHarnessArgs()`. Return stdout/stderr and exit status as tool output. Redact environment values by default; never echo `OPENAI_API_KEY`, tokens, or secrets.

- [ ] **Step 5: Wire launcher**

```js
if (command === "mcp") {
  await startMcpServer({ cwd: process.cwd() });
}
```

- [ ] **Step 6: Verify**

```bash
cd packages/rpa-harness-agent
npm test
node bin/rpa-harness-agent.js mcp
```

Expected: MCP server starts on stdio and exposes only the approved tools.

- [ ] **Step 7: Commit**

```bash
git add packages/rpa-harness-agent
git commit -m "feat: expose governed mcp bridge"
```

---

## Task 7: Product smoke test from a blank folder

**Files:**
- Create: `tests/test_product_smoke.py` or `packages/rpa-harness-agent/test/product-smoke.test.js`
- Modify: `.github/workflows/product-package.yml`

- [ ] **Step 1: Write smoke flow**

The smoke test must run from a temp directory and prove:

1. `rpa-harness-agent init` creates the workspace.
2. `rpa-harness-agent validate workflows/example.yaml` passes.
3. `rpa-harness-agent preflight workflows/example.yaml` passes.
4. `rpa-harness-agent run workflows/example.yaml` creates a run folder.
5. `rpa-harness-agent runs-list` shows the run.

- [ ] **Step 2: Add CI package job**

```yaml
name: product-package

on:
  pull_request:
  push:
    branches: [main]

jobs:
  package-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: python -m pip install -e .[test]
      - run: pytest tests/test_cli_entrypoint.py tests/test_product_init.py -v
      - run: npm test
        working-directory: packages/rpa-harness-agent
      - run: npm pack --dry-run
        working-directory: packages/rpa-harness-agent
```

- [ ] **Step 3: Verify locally**

```bash
pytest tests/test_cli_entrypoint.py tests/test_product_init.py -v
cd packages/rpa-harness-agent
npm test
npm pack --dry-run
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests packages/rpa-harness-agent .github/workflows/product-package.yml
git commit -m "test: add product package smoke coverage"
```

---

## Task 8: Document the product path

**Files:**
- Modify: `README.md`
- Create: `packages/rpa-harness-agent/README.md`
- Modify: `docs/okf` only if this becomes durable package/CLI knowledge.

- [ ] **Step 1: Add README quickstart**

```markdown
## Install as an AI-agent workspace product

```bash
npx @rpa-harness/agent init
npx @rpa-harness/agent serve
```

This creates an agent-ready local workspace with:

- `workflows/` for deterministic YAML workflows
- `.agents/` for rules, skills, and allowlisted commands
- `runs/` for evidence-backed run artifacts
- `reports/` for generated HTML/JSON reports

Connect your AI agent to the MCP command:

```bash
npx @rpa-harness/agent mcp
```

The agent can validate, preflight, run, inspect, and repair workflows through allowlisted tools only. It cannot execute arbitrary shell commands.
```

- [ ] **Step 2: Document safety model**

Include:

```text
Action execution is not success. Workflows pass only when explicit success checks pass.
Secrets are referenced by name and resolved only at the execution edge.
All AI-agent execution goes through allowlisted tools.
Every run writes timeline, manifest, report, and repair evidence where applicable.
```

- [ ] **Step 3: Verify docs commands**

```bash
python main.py --validate-yaml workflows/examples/default_schema_example.yaml
```

If OKF concepts changed:

```bash
python scripts/okf.py generate-indexes docs/okf
python scripts/okf.py validate docs/okf
```

- [ ] **Step 4: Commit**

```bash
git add README.md packages/rpa-harness-agent/README.md docs/okf
git commit -m "docs: explain npm agent product install"
```

---

## Task 9: Prepare publishing without actually publishing

**Files:**
- Create: `scripts/check_product_release.py`
- Modify: `packages/rpa-harness-agent/package.json`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add release checklist script**

The script should check:

1. Python version and npm version are aligned.
2. `npm pack --dry-run` passes.
3. `python -m build` passes.
4. Product smoke tests pass.
5. Package READMEs exist.

- [ ] **Step 2: Verify package metadata**

Python:

```toml
[project]
name = "rpa-harness"
version = "0.1.0"
license = "MIT"
```

npm:

```json
{
  "name": "@rpa-harness/agent",
  "version": "0.1.0",
  "license": "MIT"
}
```

- [ ] **Step 3: Run dry release checks**

```bash
python -m pip install build
python -m build
cd packages/rpa-harness-agent
npm pack --dry-run
```

Expected: wheel, sdist, and npm tarball are created/dry-run cleanly.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_product_release.py pyproject.toml packages/rpa-harness-agent/package.json
git commit -m "chore: add product release checks"
```

---

## Execution Order

1. Python CLI package entrypoint.
2. Workspace initializer.
3. npm launcher.
4. npm init/install flow.
5. governed command wrappers.
6. MCP bridge.
7. blank-folder smoke test.
8. docs.
9. dry release checks.

This order keeps every slice runnable. Do not start MCP before `npx init` can create and validate a workspace.

---

## Acceptance Criteria

- A new user can run:

```bash
npx @rpa-harness/agent init
npx @rpa-harness/agent validate workflows/example.yaml
npx @rpa-harness/agent serve
```

- An AI agent can connect with:

```bash
npx @rpa-harness/agent mcp
```

- The MCP bridge exposes only allowlisted tools.
- A workflow run produces `run_manifest.json`, `timeline.jsonl`, and `report.html`.
- No secret values are logged or returned through MCP.
- CI proves Python tests, Node tests, and package dry-runs.

---

## Self-Review

- Spec coverage: The plan covers install, workspace creation, agent folder connection, governed execution, MCP bridge, tests, docs, and publishing preparation.
- Placeholder scan: No `TBD`, `TODO`, or "implement later" placeholders remain.
- Type consistency: Node command names map consistently from CLI command wrappers to MCP tool names.
- YAGNI check: The plan skips cloud, accounts, billing, package marketplace automation, and custom protocol code. Those come after the local product loop works.
