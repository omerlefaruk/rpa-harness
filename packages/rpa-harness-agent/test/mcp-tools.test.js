import test from "node:test";
import assert from "node:assert/strict";
import { toolToCommand, listMcpTools } from "../lib/mcp-server.js";
import { buildHarnessArgs } from "../lib/commands.js";

test("full agent-loop MCP tools are allowlisted", () => {
  const tools = listMcpTools();
  for (const name of [
    "propose_automation",
    "execute_automation_read",
    "execute_automation_write",
    "reconcile_automation_run",
    "propose_automation_repair",
    "trial_automation_repair",
    "promote_automation_repair",
    "inspect_automation_run",
  ]) {
    assert.ok(tools.includes(name), name);
  }
});

test("execute write maps to CLI adapter", () => {
  assert.deepEqual(
    toolToCommand("execute_automation_write", {
      request_path: "requests/write.json",
      workspace: ".rpa-automation",
    }),
    {
      command: "automation-execute-write",
      args: ["requests/write.json", ".rpa-automation"],
    },
  );
  assert.deepEqual(
    buildHarnessArgs("automation-execute-write", [
      "requests/write.json",
      ".rpa-automation",
    ]),
    [
      "-m",
      "harness.cli",
      "--automation-execute-write",
      "requests/write.json",
      "--automation-workspace",
      ".rpa-automation",
    ],
  );
});

test("shell and yaml runner escape hatches are not MCP tools", () => {
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

test("path traversal is rejected", () => {
  assert.throws(() =>
    buildHarnessArgs("automation-execute-write", ["../x.json", ".ws"]),
  );
});
