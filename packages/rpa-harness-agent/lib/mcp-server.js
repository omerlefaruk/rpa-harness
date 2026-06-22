import readline from "node:readline";
import { spawnSync } from "node:child_process";
import { buildHarnessArgs } from "./commands.js";

const TOOLS = [
  ["validate_workflow", "validate", "workflow_path"],
  ["preflight_workflow", "preflight", "workflow_path"],
  ["run_workflow", "run", "workflow_path"],
  ["list_runs", "runs-list"],
  ["show_run", "runs-show", "run_id"],
  ["open_report", "report-open", "run_id"],
  ["repair_selector", "repair-selector", "run_dir"],
];

export function toolToCommand(tool, input = {}) {
  const match = TOOLS.find(([name]) => name === tool);
  if (!match) throw new Error(`Unknown MCP tool: ${tool}`);
  const [, command, field] = match;
  return { command, args: field ? [input[field]] : [] };
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
      serverInfo: { name: "rpa-harness-agent", version: "0.1.0" },
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

function toolSchema([name, , field]) {
  return {
    name,
    inputSchema: {
      type: "object",
      properties: field ? { [field]: { type: "string" } } : {},
      required: field ? [field] : [],
    },
  };
}

function send(id, result) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`);
}

function redact(text) {
  return text.replace(/sk-[A-Za-z0-9_-]+/g, "[REDACTED]");
}
