import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import process from "node:process";

export const DEFAULT_PYTHON_SOURCE = "rpa-harness==0.1.0";

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

export function buildPythonInstallArgs(
  packageSource = process.env.RPA_HARNESS_PYTHON_SOURCE || DEFAULT_PYTHON_SOURCE,
) {
  const editable = packageSource.startsWith(".") || packageSource.startsWith("/");
  return editable
    ? ["-m", "pip", "install", "-e", packageSource]
    : ["-m", "pip", "install", "--upgrade", packageSource];
}

export function ensureRuntime(cwd = process.cwd()) {
  const paths = runtimePaths(cwd);
  if (!fs.existsSync(paths.python)) {
    fs.mkdirSync(paths.root, { recursive: true });
    runChecked(process.env.PYTHON || "python", ["-m", "venv", paths.venv]);
  }
  runChecked(paths.python, buildPythonInstallArgs());
  return paths;
}

export function runChecked(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: "inherit", ...options });
  if (result.status !== 0) process.exit(result.status ?? 1);
  return result;
}
