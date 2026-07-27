import path from "node:path";

// ActiveGraph-native allowlist only. YAML/shell/raw-driver commands are not exposed.
const COMMANDS = {
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
  const tokens = [];
  let argIndex = 0;
  for (const flag of mapped.flags) {
    tokens.push(flag);
    if (flag === "--automation-list-operations" || flag === "--automation-workspace-status") {
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
