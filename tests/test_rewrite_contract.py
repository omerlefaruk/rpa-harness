from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from harness.automation import (
    AutomationApplication,
    Principal,
    ToolResult,
    VerificationResult,
    discover_skills,
    validate_source,
)
from harness.automation.agent_ops import execute_write_request
from harness.automation.credentials import CredentialService, InMemoryCredentialBackend
from harness.mcp_server import _cli_args, handle_request


def test_source_validation_fails_closed_for_direct_effects_and_unpinned_deps():
    validation = validate_source(
        "from pathlib import Path\nPath('x').write_text('bad')\n",
        dependency_lock="httpx>=0.1",
        declared_action_class="R0",
    )
    assert not validation.accepted
    assert any("outside an Action Boundary" in error for error in validation.errors)
    assert any("unpinned dependency" in error for error in validation.errors)


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef main(payload):\n    os.system('echo unsafe')\n",
        "import shutil\ndef main(payload):\n    shutil.rmtree(payload['path'])\n",
        "import typing\ndef main(payload):\n    typing.sys.stdout.write('unsafe')\n",
        "def main(payload):\n    payload['callback']()\n",
        "def invoke(check):\n"
        "    return check(\"__import__('os').system('echo unsafe')\")\n"
        "def main(payload):\n"
        "    return invoke(__builtins__['eval'])\n",
        "def main(payload):\n"
        "    return list(map(eval, [\"__import__('os').system('echo unsafe')\"]))\n",
        "import typing\n"
        "def main(payload):\n"
        "    callback = typing.sys.stdout.write\n"
        "    return list(map(callback, ['unsafe']))\n",
        "import operator\n"
        "def helper():\n"
        "    return None\n"
        "def main(payload):\n"
        "    namespace = list(map(operator.attrgetter('__globals__'), [helper]))[0]\n"
        "    opener = namespace.get('__builtins__').get('open')\n"
        "    handle = list(map(opener, [payload.get('path')]))[0]\n"
        "    return list(map(operator.methodcaller('read'), [handle]))[0]\n",
        "def helper():\n"
        "    return None\n"
        "def read():\n"
        "    return None\n"
        "def main(payload):\n"
        "    builtins = helper.__globals__.get('__builtins__')\n"
        "    opener = builtins.get('open')\n"
        "    handles = list(map(opener, [payload['path']]))\n"
        "    return handles[0].read()\n",
        "def main(payload):\n"
        "    callback = payload.get('callback')\n"
        "    return list(map(callback, payload.get('values')))\n",
        "from datetime import datetime\n"
        "def main(payload):\n"
        "    return {'time': datetime.now().isoformat()}\n",
        "import typing\n"
        "def main(payload):\n"
        "    namespace = typing\n"
        "    values = namespace.__dict__\n"
        "    return values.get('sys')\n",
    ],
)
def test_source_validation_rejects_unknown_effects(source):
    validation = validate_source(source, declared_action_class="R0")
    assert not validation.accepted
    assert any("unsupported" in error for error in validation.errors)


def test_source_validation_accepts_analyzed_local_class_construction():
    validation = validate_source(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Row:\n"
        "    value: int\n"
        "def main(payload):\n"
        "    row = Row(int(payload['value']))\n"
        "    return {'value': row.value}\n"
    )
    assert validation.accepted, validation.errors


def test_source_validation_accepts_future_annotations():
    validation = validate_source(
        "from __future__ import annotations\n"
        "def main(payload: dict[str, object]):\n"
        "    return payload\n"
    )
    assert validation.accepted, validation.errors


def test_source_validation_rejects_rebound_trusted_callable():
    validation = validate_source(
        "def helper():\n"
        "    return None\n"
        "def main(payload):\n"
        "    helper = __builtins__['open']\n"
        "    helper(payload['path'], 'w')\n"
    )
    assert not validation.accepted
    assert "unsupported rebound call target: helper" in validation.errors


def test_source_snapshot_is_immutable_and_worker_uses_snapshot(tmp_path):
    workspace = tmp_path / "workspace"
    app = AutomationApplication(workspace)
    version = app.register_source(
        definition_id="snapshot-read",
        name="Snapshot read",
        success_check="result is present",
        source="def main(payload):\n    return {'value': payload['value']}\n",
    )
    assert version.definition.source_hash
    registered = next(path for path in (workspace / "snapshots").glob("*.py"))
    assert registered.read_bytes() == (
        b"def main(payload):\n    return {'value': payload['value']}\n"
    )
    response = app.run_snapshot(
        registered,
        request_id="req-1",
        payload={"value": 3},
    )
    assert response.ok is True
    assert response.value == {"value": 3}

    outside = tmp_path / "outside.py"
    outside.write_text("def main(payload):\n    return payload\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="registered snapshots"):
        app.run_snapshot(outside, request_id="req-outside")

    unregistered = workspace / "snapshots" / "unregistered.py"
    unregistered.write_text("def main(payload):\n    return payload\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="registered snapshot"):
        app.run_snapshot(unregistered, request_id="req-unregistered")

    registered.write_text("def main(payload):\n    return {'tampered': True}\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="content hash mismatch"):
        app.run_snapshot(registered, request_id="req-tampered")
    app.close()


def test_agent_principal_cannot_grant_or_write(tmp_path):
    app = AutomationApplication(tmp_path / "workspace")
    with pytest.raises(PermissionError, match="operator"):
        app.grant_approval(
            definition_id="missing",
            version=1,
            actor="agent",
            target_scope="",
            record_scope="",
            side_effect_scope="",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            principal=Principal("agent", "model"),
        )
    credentials = CredentialService(InMemoryCredentialBackend())
    with pytest.raises(PermissionError):
        credentials.create("token", "secret", actor="model", principal=Principal("agent", "model"))
    app.close()


def test_graph_queries_and_content_addressed_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    app = AutomationApplication(workspace)
    from harness.automation import AutomationDefinition

    app.register_definition(AutomationDefinition("read", "Read", "value is present"))
    assert app.graph_automations()[0]["definition_id"] == "read"
    summary = app.execute_read_only(
        "read",
        lambda _definition, _run_id: ToolResult(value={"value": 1}, evidence={"same": True}),
        lambda result: VerificationResult(passed=bool(result.value.get("value"))),
    )
    path = workspace / summary.evidence_references[0].uri
    assert path.exists()
    assert summary.evidence_references[0].content_hash in path.name
    app.close()
    reopened = AutomationApplication(workspace, read_only=True)
    assert reopened.graph_automations()[0]["definition_id"] == "read"
    assert reopened.inspect_run(summary.run_id).status == "completed"
    reopened.close()


def test_python_mcp_exposes_skills_and_no_operator_grant_tool():
    initialized = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["serverInfo"]["name"] == "rpa-harness"
    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {item["name"] for item in listed["result"]["tools"]}
    assert "list_feature_skills" in names
    assert "grant_approval" not in names
    assert discover_skills()


def test_python_mcp_workspace_tools_emit_workspace_flag():
    assert _cli_args("workspace_status", {"workspace": "ws"}) == [
        "--automation-workspace-status",
        "--automation-workspace",
        "ws",
    ]
    assert _cli_args(
        "execute_automation_read",
        {"request_path": "request.json", "workspace": "ws"},
    ) == [
        "--automation-execute-read",
        "request.json",
        "--automation-workspace",
        "ws",
    ]


def test_agent_write_adapter_preserves_agent_principal():
    captured = {}

    class Summary:
        def to_dict(self):
            return {"ok": True}

    class FakeApplication:
        def execute_write(self, *args, **kwargs):
            captured.update(kwargs)
            return Summary()

    request = {
        "definition_id": "write",
        "version": 1,
        "grant_id": "grant",
        "actor": "model",
        "op": {"name": "write", "action_class": "R2", "read_only": False},
        "fixture_result": {"value": {"written": True}},
    }
    assert execute_write_request(FakeApplication(), request) == {"ok": True}
    assert captured["principal"] == "agent"
