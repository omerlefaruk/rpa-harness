import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { buildPythonInstallArgs, runtimePaths } from "../lib/python-runtime.js";

test("runtime paths stay inside the workspace", () => {
  const paths = runtimePaths(path.join("tmp", "example-product"));

  assert.equal(paths.root, path.join("tmp", "example-product", ".rpa-harness"));
  assert.match(paths.python, /\.rpa-harness/);
});

test("local source install uses editable mode", () => {
  assert.deepEqual(buildPythonInstallArgs("../../.."), ["-m", "pip", "install", "-e", "../../.."]);
});
