import test from "node:test";
import assert from "node:assert/strict";
import { buildHarnessArgs } from "../lib/commands.js";

test("automation validate maps to the application CLI adapter", () => {
  assert.deepEqual(buildHarnessArgs("automation-validate-proposal", ["proposals/inventory.json"]), [
    "-m",
    "harness.cli",
    "--automation-validate-proposal",
    "proposals/inventory.json",
  ]);
});

test("unknown command is rejected", () => {
  assert.throws(() => buildHarnessArgs("shell", ["rm", "-rf", "."]));
  assert.throws(() => buildHarnessArgs("validate", ["workflows/example.yaml"]));
  assert.throws(() => buildHarnessArgs("run", ["workflows/example.yaml"]));
});

test("path traversal is rejected", () => {
  assert.throws(() =>
    buildHarnessArgs("automation-validate-proposal", ["../outside.json"]),
  );
});
