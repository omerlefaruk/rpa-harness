"""Official Python MCP-compatible JSON-RPC server over the application seam."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from harness.automation.principals import Principal
from harness.automation.operations import CATALOG_VERSION, list_operations
from harness.automation.skills import discover_skills


SERVER_VERSION = "0.2.0"
CLI_TOOL_ARGS: dict[str, tuple[str, ...]] = {
    "init_workspace": ("--automation-init-workspace", "workspace"),
    "workspace_status": ("--automation-workspace-status", "workspace"),
    "propose_automation": ("--automation-propose", "request_path", "workspace"),
    "validate_automation_proposal": ("--automation-validate-proposal", "proposal_path"),
    "register_automation_proposal": (
        "--automation-register-proposal",
        "proposal_path",
        "workspace",
    ),
    "execute_automation_read": ("--automation-execute-read", "request_path", "workspace"),
    "execute_automation_write": ("--automation-execute-write", "request_path", "workspace"),
    "reconcile_automation_run": ("--automation-reconcile", "request_path", "workspace"),
    "propose_automation_repair": (
        "--automation-propose-repair",
        "request_path",
        "workspace",
    ),
    "trial_automation_repair": ("--automation-trial-repair", "request_path", "workspace"),
    "promote_automation_repair": (
        "--automation-promote-repair",
        "request_path",
        "workspace",
    ),
    "inspect_automation_run": ("--automation-inspect", "run_id", "workspace"),
    "export_automation_evidence": ("--automation-export-evidence", "run_id", "workspace"),
}

TOOL_NAMES = (
    "list_automation_operations",
    "list_feature_skills",
    "read_feature_skill",
    "validate_source",
    "request_approval",
    *CLI_TOOL_ARGS.keys(),
)


def resource_list() -> list[dict[str, Any]]:
    return [
        {
            "uri": f"rpa://skills/{skill.name}",
            "name": skill.name,
            "mimeType": "text/markdown",
        }
        for skill in discover_skills()
    ]


def handle_request(request: dict[str, Any], *, app_factory: Callable[[str, bool], Any] | None = None) -> dict[str, Any]:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "rpa-harness", "version": SERVER_VERSION},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": name,
                    "description": f"Agent-safe ActiveGraph operation: {name}",
                    "inputSchema": _tool_schema(name),
                }
                for name in TOOL_NAMES
            ]
        }
    elif method == "resources/list":
        result = {"resources": resource_list()}
    elif method == "resources/read":
        uri = str((request.get("params") or {}).get("uri", ""))
        name = uri.removeprefix("rpa://skills/")
        from harness.automation.skills import get_skill

        skill = get_skill(name)
        result = {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": skill.content}]}
    elif method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name", ""))
        arguments = dict(params.get("arguments") or {})
        if name not in TOOL_NAMES:
            raise ValueError(f"unknown MCP tool: {name}")
        if name == "list_automation_operations":
            value = {"catalog_version": CATALOG_VERSION, "operations": [item.to_dict() for item in list_operations()]}
            result = {"content": [{"type": "text", "text": json.dumps(value)}]}
        elif name == "request_approval":
            if app_factory is None:
                raise ValueError("application factory is not configured")
            workspace = str(arguments["workspace"])
            app = app_factory(workspace, False)
            try:
                value = app.execute_command("request_approval", arguments, principal="agent")
            finally:
                app.close()
            result = {"isError": not value.ok, "content": [{"type": "text", "text": json.dumps(value.to_dict())}]}
        elif name == "list_feature_skills":
            result = {"content": [{"type": "text", "text": json.dumps([skill.to_dict() for skill in discover_skills()])}]}
        elif name == "read_feature_skill":
            from harness.automation.skills import get_skill

            result = {"content": [{"type": "text", "text": get_skill(str(arguments["name"])).content}]}
        elif name == "validate_source":
            from harness.automation.source_validation import validate_source

            result = {"content": [{"type": "text", "text": json.dumps(validate_source(str(arguments.get("source", ""))).to_dict())}]}
        elif name in CLI_TOOL_ARGS:
            argv = _cli_args(name, arguments)
            completed = subprocess.run(
                [sys.executable, "-m", "harness.cli", *argv],
                check=False,
                capture_output=True,
                text=True,
            )
            output = (completed.stdout or completed.stderr or "").strip()
            result = {
                "isError": completed.returncode != 0,
                "content": [{"type": "text", "text": output or f"exit {completed.returncode}"}],
            }
        elif app_factory is None:
            result = {"content": [{"type": "text", "text": "application factory is not configured"}]}
        else:
            workspace = str(arguments["workspace"])
            app = app_factory(workspace, True)
            try:
                if name == "workspace_status":
                    value = app.graph_status()
                else:
                    value = app.inspect_run(str(arguments["run_id"])).to_dict()
            finally:
                app.close()
            result = {"content": [{"type": "text", "text": json.dumps(value, default=str)}]}
    else:
        raise ValueError(f"unsupported MCP method: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _tool_schema(name: str) -> dict[str, Any]:
    if name == "list_automation_operations":
        fields: tuple[str, ...] = ()
    elif name in {"list_feature_skills", "read_feature_skill", "validate_source", "request_approval"}:
        fields = {
            "list_feature_skills": (),
            "read_feature_skill": ("name",),
            "validate_source": ("source",),
            "request_approval": ("workspace", "revision", "scope", "reason"),
        }[name]
    else:
        fields = tuple(field for field in CLI_TOOL_ARGS[name] if not field.startswith("--"))
    return {
        "type": "object",
        "properties": {field: {"type": "string"} for field in fields},
        "required": list(fields),
    }


def _cli_args(name: str, arguments: dict[str, Any]) -> list[str]:
    values = CLI_TOOL_ARGS[name]
    argv: list[str] = []
    for value in values:
        if value.startswith("--"):
            argv.append(value)
            continue
        if value not in arguments:
            raise ValueError(f"MCP tool {name} requires argument {value}")
        argv.append(str(arguments[value]))
    return argv


def serve() -> None:
    from harness.automation.application import AutomationApplication

    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle_request(request, app_factory=lambda workspace, read_only: AutomationApplication(workspace, read_only=read_only))
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, default=str) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve()
