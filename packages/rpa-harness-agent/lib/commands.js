import path from "node:path";

const COMMANDS = {
  validate: { flags: ["--validate-yaml"], args: 1 },
  preflight: { flags: ["--preflight-yaml"], args: 1 },
  run: { flags: ["--run-yaml"], args: 1 },
  "runs-list": { flags: ["--runs-list"], args: 0 },
  "runs-show": { flags: ["--runs-show"], args: 1 },
  "report-open": { flags: ["--report-open"], args: 1 },
  "repair-selector": { flags: ["--repair-selector"], args: 1 },
  "automation-list-operations": {
    flags: ["--automation-list-operations"],
    args: 0,
  },
  "automation-validate-proposal": {
    flags: ["--automation-validate-proposal"],
    args: 1,
  },
  "automation-register-proposal": {
    flags: ["--automation-register-proposal", "--automation-workspace"],
    args: 2,
  },
  "automation-inspect": {
    flags: ["--automation-inspect", "--automation-workspace"],
    args: 2,
  },
  "automation-export-evidence": {
    flags: ["--automation-export-evidence", "--automation-workspace"],
    args: 2,
  },
  "automation-grant-approval": {
    flags: ["--automation-grant-approval", "--automation-workspace"],
    args: 2,
  },
  "automation-workspace-status": {
    flags: ["--automation-workspace-status", "--automation-workspace"],
    args: 1,
  },
};

export function buildHarnessArgs(command, args = []) {
  const mapped = COMMANDS[command];
  if (!mapped) throw new Error(`Command is not allowlisted: ${command}`);
  if (args.length !== mapped.args) throw new Error(`Expected ${mapped.args} argument(s) for ${command}`);
  const safeArgs = args.map(safePathArg);
  // Interleave each flag with its value so argparse receives --flag value pairs.
  const tokens = [];
  let argIndex = 0;
  for (const flag of mapped.flags) {
    tokens.push(flag);
    // Boolean store_true flags consume no value.
    if (
      flag === "--automation-list-operations" ||
      flag === "--automation-workspace-status" ||
      flag === "--runs-list"
    ) {
      continue;
    }
    if (argIndex < safeArgs.length) {
      tokens.push(safeArgs[argIndex]);
      argIndex += 1;
    }
  }
  while (argIndex < safeArgs.length) {
    tokens.push(safeArgs[argIndex]);
    argIndex += 1;
  }
  return ["-m", "harness.cli", ...tokens];
}

function safePathArg(value) {
  if (typeof value !== "string" || !value || value.includes("\0")) {
    throw new Error("Invalid command argument");
  }
  if (path.isAbsolute(value) || value.split(/[\\/]/).includes("..")) {
    throw new Error(`Argument must stay inside the workspace: ${value}`);
  }
  return value;
}
