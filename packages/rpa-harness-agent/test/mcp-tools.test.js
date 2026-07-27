import test from "node:test";
import assert from "node:assert/strict";
import { toolToCommand } from "../lib/mcp-server.js";

test("run_workflow maps to the allowlisted run command", () => {
  assert.deepEqual(toolToCommand("run_workflow", { workflow_path: "workflows/example.yaml" }), {
    command: "run",
    args: ["workflows/example.yaml"],
  });
});

test("unknown MCP tools are rejected", () => {
  assert.throws(() => toolToCommand("shell", {}));
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
