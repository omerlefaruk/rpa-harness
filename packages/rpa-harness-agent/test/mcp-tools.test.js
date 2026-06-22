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
