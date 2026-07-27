import test from "node:test";
import assert from "node:assert/strict";
import { toolToCommand } from "../lib/mcp-server.js";

test("unknown MCP tools are rejected", () => {
  assert.throws(() => toolToCommand("shell", {}));
});

test("automation validation stays on an allowlisted application operation", () => {
  assert.deepEqual(
    toolToCommand("validate_automation_proposal", {
      proposal_path: "proposals/inventory.json",
    }),
    {
      command: "automation-validate-proposal",
      args: ["proposals/inventory.json"],
    },
  );
});

test("automation registration stays on an allowlisted application operation", () => {
  assert.deepEqual(
    toolToCommand("register_automation_proposal", {
      proposal_path: "proposals/inventory.json",
      workspace: ".rpa-automation",
    }),
    {
      command: "automation-register-proposal",
      args: ["proposals/inventory.json", ".rpa-automation"],
    },
  );
});

test("shell and raw driver escape hatches are not MCP tools", () => {
  for (const name of [
    "shell",
    "exec",
    "run_python",
    "raw_driver",
    "playwright_click",
    "run_workflow",
    "validate_workflow",
  ]) {
    assert.throws(() => toolToCommand(name, {}));
  }
});

test("operation catalog and inspect tools stay allowlisted", () => {
  assert.deepEqual(toolToCommand("list_automation_operations", {}), {
    command: "automation-list-operations",
    args: [],
  });
  assert.deepEqual(
    toolToCommand("inspect_automation_run", {
      run_id: "run_1",
      workspace: ".rpa-automation",
    }),
    {
      command: "automation-inspect",
      args: ["run_1", ".rpa-automation"],
    },
  );
  assert.deepEqual(
    toolToCommand("workspace_status", { workspace: ".rpa-automation" }),
    {
      command: "automation-workspace-status",
      args: [".rpa-automation"],
    },
  );
});
