"""Thin CLI adapter over AutomationApplication. No lifecycle logic here."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from harness.activegraph_app.application import ApplicationError, AutomationApplication
from harness.activegraph_app.workspace import WorkspaceError, WorkspaceLockError


def build_ag_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rpa-harness ag",
        description="ActiveGraph-native automation application CLI",
    )
    sub = parser.add_subparsers(dest="ag_command", required=True)

    init_p = sub.add_parser("init-workspace", help="Initialize a local workspace")
    init_p.add_argument("workspace", type=Path)

    reg = sub.add_parser("register-definition", help="Register a read-only definition version")
    reg.add_argument("workspace", type=Path)
    reg.add_argument("--name", required=True)
    reg.add_argument("--target", required=True)
    reg.add_argument("--success-check", required=True, choices=["equals", "exists"])
    reg.add_argument("--expected-value")
    reg.add_argument("--definition-id")
    reg.add_argument("--version", default="1")

    run_p = sub.add_parser("run", help="Execute a registered read-only definition")
    run_p.add_argument("workspace", type=Path)
    run_p.add_argument("--definition-id", required=True)
    run_p.add_argument("--version", default="1")
    run_p.add_argument("--run-id")

    inspect_p = sub.add_parser("inspect-run", help="Inspect a run without taking the write lock")
    inspect_p.add_argument("workspace", type=Path)
    inspect_p.add_argument("--run-id", required=True)

    return parser


def _print_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run_ag_cli(argv: Sequence[str] | None = None) -> int:
    parser = build_ag_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    app = AutomationApplication(args.workspace, store_kind="sqlite")

    try:
        if args.ag_command == "init-workspace":
            info = app.init_workspace()
            _print_json(info.to_dict())
            return 0
        if args.ag_command == "register-definition":
            app.init_workspace()
            summary = app.register_readonly_definition(
                name=args.name,
                target=args.target,
                success_check=args.success_check,
                expected_value=args.expected_value,
                definition_id=args.definition_id,
                version=args.version,
            )
            _print_json(summary.to_dict())
            return 0
        if args.ag_command == "run":
            summary = app.execute_readonly_run(
                definition_id=args.definition_id,
                version=args.version,
                run_id=args.run_id,
            )
            _print_json(summary.to_dict())
            return 0 if summary.status == "completed" else 2
        if args.ag_command == "inspect-run":
            summary = app.inspect_run(args.run_id)
            _print_json(summary.to_dict())
            return 0
    except (ApplicationError, WorkspaceError, WorkspaceLockError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    parser.error(f"unknown command: {args.ag_command}")
    return 2
