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

test("path traversal is rejected", () => {
  assert.throws(() => buildHarnessArgs("validate", ["../outside.yaml"]));
});
