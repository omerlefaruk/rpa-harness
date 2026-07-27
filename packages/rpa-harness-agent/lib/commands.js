import path from "node:path";

const COMMANDS = {
  validate: { flags: ["--validate-yaml"], args: 1 },
  preflight: { flags: ["--preflight-yaml"], args: 1 },
  run: { flags: ["--run-yaml"], args: 1 },
  "runs-list": { flags: ["--runs-list"], args: 0 },
  "runs-show": { flags: ["--runs-show"], args: 1 },
  "report-open": { flags: ["--report-open"], args: 1 },
  "repair-selector": { flags: ["--repair-selector"], args: 1 },
  "automation-validate-proposal": {
    flags: ["--automation-validate-proposal"],
    args: 1,
  },
  "automation-register-proposal": {
    flags: ["--automation-register-proposal", "--automation-workspace"],
    args: 2,
  },
};

export function buildHarnessArgs(command, args = []) {
  const mapped = COMMANDS[command];
  if (!mapped) throw new Error(`Command is not allowlisted: ${command}`);
  if (args.length !== mapped.args) throw new Error(`Expected ${mapped.args} argument(s) for ${command}`);
  return ["-m", "harness.cli", ...mapped.flags, ...args.map(safePathArg)];
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
