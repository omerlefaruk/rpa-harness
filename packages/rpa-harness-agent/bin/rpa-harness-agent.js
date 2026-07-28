#!/usr/bin/env node
import process from "node:process";
import { buildHarnessArgs, listAllowlistedCommands } from "../lib/commands.js";
import { ensureRuntime, runChecked, runtimePaths } from "../lib/python-runtime.js";

const [command, ...args] = process.argv.slice(2);

if (!command || command === "--help" || command === "help") {
  console.log(`rpa-harness-agent — ActiveGraph-native MCP/CLI launcher

Usage:
  rpa-harness-agent init [workspace]
  rpa-harness-agent mcp
  rpa-harness-agent <allowlisted-command> [args...]

Allowlisted commands (no shell / no YAML runner / no raw drivers):
  ${listAllowlistedCommands().join("\n  ")}

Agent loop (AI writes JSON files, then calls tools):
  1. init workspace
  2. propose / validate / register proposal JSON
  3. grant approval JSON (R3/R4 writes)
  4. execute-read or execute-write request JSON
  5. inspect run / export evidence
  6. reconcile or repair if needed
`);
  process.exit(0);
}

if (command === "init") {
  const paths = ensureRuntime();
  const workspace = args[0] || process.cwd();
  // Paths must stay relative for the allowlist when used via MCP; CLI init may be cwd.
  runChecked(paths.python, [
    "-m",
    "harness.cli",
    "--automation-init-workspace",
    workspace,
  ]);
  console.log(`ActiveGraph workspace ready at ${workspace}`);
  console.log("Start MCP: rpa-harness-agent mcp");
  process.exit(0);
}

const python = runtimePaths().python;

if (command === "mcp") {
  const paths = ensureRuntime();
  runChecked(paths.python, ["-m", "harness.mcp_server"]);
} else {
  runChecked(python, buildHarnessArgs(command, args));
}
