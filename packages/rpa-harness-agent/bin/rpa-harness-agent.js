#!/usr/bin/env node
import process from "node:process";
import { buildHarnessArgs } from "../lib/commands.js";
import { ensureRuntime, runChecked, runtimePaths } from "../lib/python-runtime.js";
import { startMcpServer } from "../lib/mcp-server.js";

const [command, ...args] = process.argv.slice(2);

if (!command || command === "--help" || command === "help") {
  console.log("Usage: rpa-harness-agent <init|serve|mcp|validate|preflight|run|runs-list|runs-show|report-open|repair-selector> [arg]");
  process.exit(0);
}

if (command === "init") {
  const paths = ensureRuntime();
  runChecked(paths.python, ["-m", "harness.cli", "--init-workspace", process.cwd()]);
  console.log("Ready. Try: rpa-harness-agent validate workflows/example.yaml");
  process.exit(0);
}

const python = runtimePaths().python;

if (command === "serve") {
  runChecked(python, ["-m", "harness.cli", "--serve", "--port", args[0] || "8080"]);
}

if (command === "mcp") {
  startMcpServer(python);
} else {
  runChecked(python, buildHarnessArgs(command, args));
}
