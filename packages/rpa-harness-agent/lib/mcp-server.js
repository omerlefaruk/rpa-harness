import readline from "node:readline";
import { spawnSync } from "node:child_process";
import { buildHarnessArgs } from "./commands.js";

/**
 * MCP tools for the full ActiveGraph agent loop.
 * No shell, no raw driver, no YAML runner — only application operations.
 *
 * Typical agent sequence:
 *   init_workspace → propose → validate → register → grant → execute_* → inspect
 *   on unknown write: reconcile
 *   on selector failure: propose_repair → trial_repair → promote_repair
 */
const TOOLS = [
  ["list_automation_operations", "automation-list-operations"],
  ["init_workspace", "automation-init-workspace", "workspace"],
  ["workspace_status", "automation-workspace-status", "workspace"],
  ["propose_automation", "automation-propose", "request_path", "workspace"],
  ["validate_automation_proposal", "automation-validate-proposal", "proposal_path"],
  ["register_automation_proposal", "automation-register-proposal", "proposal_path", "workspace"],
  ["grant_automation_approval", "automation-grant-approval", "grant_path", "workspace"],
  ["execute_automation_read", "automation-execute-read", "request_path", "workspace"],
  ["execute_automation_write", "automation-execute-write", "request_path", "workspace"],
  ["reconcile_automation_run", "automation-reconcile", "request_path", "workspace"],
  ["propose_automation_repair", "automation-propose-repair", "request_path", "workspace"],
  ["trial_automation_repair", "automation-trial-repair", "request_path", "workspace"],
  ["promote_automation_repair", "automation-promote-repair", "request_path", "workspace"],
  ["inspect_automation_run", "automation-inspect", "run_id", "workspace"],
  ["export_automation_evidence", "automation-export-evidence", "run_id", "workspace"],
];

export function toolToCommand(tool, input = {}) {
  const match = TOOLS.find(([name]) => name === tool);
  if (!match) throw new Error(`Unknown MCP tool: ${tool}`);
  const [, command, field, secondField] = match;
  return { command, args: [field, secondField].filter(Boolean).map((name) => input[name]) };
}

export function listMcpTools() {
  return TOOLS.map(([name]) => name);
}

export function startMcpServer(python) {
  const lines = readline.createInterface({ input: process.stdin });
  lines.on("line", (line) => handleLine(line, python));
}

function handleLine(line, python) {
  const request = JSON.parse(line);
  if (request.method === "initialize") {
    return send(request.id, {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "rpa-harness-agent", version: "0.2.0" },
    });
  }
  if (request.method === "tools/list") {
    return send(request.id, { tools: TOOLS.map(toolSchema) });
  }
  if (request.method === "tools/call") {
    try {
      const { command, args } = toolToCommand(request.params.name, request.params.arguments);
      const result = spawnSync(python, buildHarnessArgs(command, args), {
        encoding: "utf8",
        shell: false,
      });
      const text = redact(`${result.stdout || ""}${result.stderr || ""}`);
      return send(request.id, {
        isError: result.status !== 0,
        content: [{ type: "text", text: text || `exit ${result.status ?? 0}` }],
      });
    } catch (error) {
      return send(request.id, { isError: true, content: [{ type: "text", text: error.message }] });
    }
  }
  send(request.id, { error: `Unsupported method: ${request.method}` });
}

function toolSchema([name, , field, secondField]) {
  return {
    name,
    description: `ActiveGraph automation operation: ${name}`,
    inputSchema: {
      type: "object",
      properties: {
        ...(field ? { [field]: { type: "string" } } : {}),
        ...(secondField ? { [secondField]: { type: "string" } } : {}),
      },
      required: [field, secondField].filter(Boolean),
    },
  };
}

function send(id, result) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`);
}

function redact(text) {
  return text.replace(/sk-[A-Za-z0-9_-]+/g, "[REDACTED]");
}
